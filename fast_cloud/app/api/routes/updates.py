from __future__ import annotations

from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterator

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.storage import release_packages_dir
from app.core.entitlements import filter_products, normalise_product, licence_is_current
from app.db.session import get_db
from app.models import AuditLog, Club, ClubMember, DeviceActivation, DeviceAuditLog, Licence, Release, RemoteCommand, User

router = APIRouter(prefix="/updates", tags=["Updates"])
PACKAGES_DIR = release_packages_dir()
CHANNELS = {"stable", "beta", "alpha", "internal"}
CHUNK_SIZE = 1024 * 1024
DEPLOYMENT_RINGS = ("development", "internal", "beta", "pilot", "production")



def _normalise_product(value: str) -> str:
    return normalise_product(value)


def _licensed_components(user: User, device: DeviceActivation | None) -> set[str]:
    licence = device.licence if device is not None else None
    if licence is None:
        active = [item for item in user.licences if item.status == "active"]
        licence = active[0] if active else None
    if licence is None or not licence_is_current(licence.status, licence.expires_at):
        return {"launcher"}
    platform_admin = bool(user.is_admin and user.organisation_id is None)
    products = {
        _normalise_product(item)
        for item in filter_products(
            licence.products_json,
            role=user.role,
            is_platform_admin=platform_admin,
            assigned_products=user.products_json,
        )
    }
    role = "administrator" if platform_admin else str(user.role or "analyst").strip().lower()
    if products.intersection({"analysis", "viewer"}) and role in {"administrator", "analyst", "coach"}:
        products.add("hub")
    products.add("launcher")
    return products

def _display_channel(channel: str) -> str:
    return "alpha" if channel == "internal" else channel


def _user_can_access_device(db: Session, user: User, activation: DeviceActivation) -> bool:
    """Return True when the signed-in user may operate this registered device.

    Global Cloud administrators can manage every device. Organisation users may
    access devices attached to a club in their organisation, while individual
    licence holders and explicit club members retain access to their own devices.
    The checks use direct database queries so they do not depend on relationship
    loading state.
    """
    if bool(user.is_admin):
        return True

    licence = db.get(Licence, activation.licence_id)
    if licence is None:
        return False
    if licence.user_id == user.id:
        return True

    if licence.club_id is None:
        return False

    if user.organisation_id is not None:
        club_organisation_id = db.scalar(
            select(Club.organisation_id).where(Club.id == licence.club_id)
        )
        if club_organisation_id == user.organisation_id:
            return True

    membership_id = db.scalar(
        select(ClubMember.id).where(
            ClubMember.club_id == licence.club_id,
            ClubMember.user_id == user.id,
        )
    )
    return membership_id is not None


def _release_payload(release: Release, request: Request | None = None) -> dict[str, Any]:
    payload = {
        "release_id": release.id,
        "version": release.version,
        "package": release.package_filename,
        "sha256": release.package_sha256,
        "size": int(release.package_size or 0),
        "notes": release.release_notes or "",
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "product_target": release.product_target or "all",
        "minimum_launcher_version": release.minimum_launcher_version,
        "channel": _display_channel(release.channel),
        "deployment_ring": getattr(release, "deployment_ring", "development") or "development",
        "status": release.status,
        "rollout_percentage": int(getattr(release, "rollout_percentage", 100) or 0),
        "rollout_status": getattr(release, "rollout_status", "active") or "active",
        "mandatory": bool(getattr(release, "mandatory", False)),
        "mandatory_deadline": release.mandatory_deadline.isoformat() if getattr(release, "mandatory_deadline", None) else None,
        "install_mode": "replace_tree",
        "uninstall_supported": release.component != "launcher",
    }
    if request is not None and release.package_filename:
        payload["download_url"] = str(request.url_for("download_package", filename=release.package_filename))
    return payload


@router.get("/manifest")
def update_manifest(
    request: Request,
    channel: str = Query("stable"),
    device_id: str = Query(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the latest published release for every component in a channel."""
    requested_channel = channel.lower().strip()
    channel = "internal" if requested_channel == "alpha" else requested_channel
    if channel not in CHANNELS:
        raise HTTPException(status_code=400, detail="Unknown release channel.")

    device = None
    effective_ring = "production"
    if device_id:
        device = db.scalar(select(DeviceActivation).where(DeviceActivation.device_id == device_id, DeviceActivation.active.is_(True)))
    if device is not None:
        effective_ring = (device.deployment_ring or (device.licence.club.organisation.deployment_ring if device.licence.club and device.licence.club.organisation else None) or "production").lower()
    if effective_ring not in DEPLOYMENT_RINGS:
        effective_ring = "production"
    licensed_components = _licensed_components(user, device)
    # Release rows created by older FAST Cloud builds may contain the display
    # value ``alpha`` instead of the canonical database value ``internal``,
    # mixed-case deployment-ring values, or a NULL ring.  The Admin portal
    # normalises those values for display, which can otherwise make a release
    # look eligible while the Launcher manifest silently excludes it.
    channel_aliases = {channel}
    if channel == "internal":
        channel_aliases.add("alpha")

    releases = db.scalars(
        select(Release)
        .where(
            func.lower(Release.channel).in_(channel_aliases),
            or_(
                func.lower(Release.deployment_ring) == effective_ring,
                Release.deployment_ring.is_(None),
            ),
            func.lower(Release.status) == "published",
            Release.package_filename.is_not(None),
            Release.package_sha256.is_not(None),
        )
        .order_by(Release.component.asc(), Release.published_at.desc(), Release.id.desc())
    ).all()

    components: dict[str, dict[str, Any]] = {}
    waiting: dict[str, dict[str, Any]] = {}
    for release in releases:
        component_key = _normalise_product(release.component)
        if component_key not in licensed_components:
            continue
        if component_key in components:
            continue
        rollout_status = (getattr(release, "rollout_status", "active") or "active").lower()
        rollout_percentage = max(0, min(100, int(getattr(release, "rollout_percentage", 100) or 0)))
        if rollout_status != "active":
            waiting[component_key] = {"release_id": release.id, "version": release.version, "reason": rollout_status, "rollout_percentage": rollout_percentage}
            continue
        if rollout_percentage < 100:
            if not device_id:
                waiting[component_key] = {"release_id": release.id, "version": release.version, "reason": "device_id_required", "rollout_percentage": rollout_percentage}
                continue
            bucket = int(hashlib.sha256(f"{release.id}:{device_id}".encode("utf-8")).hexdigest()[:8], 16) % 100
            if bucket >= rollout_percentage:
                waiting[component_key] = {"release_id": release.id, "version": release.version, "reason": "waiting_for_rollout", "rollout_percentage": rollout_percentage, "device_bucket": bucket}
                continue
        components[component_key] = _release_payload(release, request)

    db.add(AuditLog(
        admin_user_id=user.id,
        action="update_checked",
        category="release",
        target_type="channel",
        target_label=_display_channel(channel),
        details=f"{user.email} checked the {_display_channel(channel)} channel in the {effective_ring} ring; {len(components)} component release(s) returned.",
    ))
    db.commit()
    return {"schema_version": 6, "channel": _display_channel(channel), "deployment_ring": effective_ring, "components": components, "waiting": waiting}


@router.post("/product-inventory")
def report_product_inventory(
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    device_id = str(payload.get("device_id") or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")
    device = db.scalar(select(DeviceActivation).where(DeviceActivation.device_id == device_id, DeviceActivation.active.is_(True)))
    if device is None:
        raise HTTPException(status_code=404, detail="Active device not found")
    products = payload.get("products", {})
    if not isinstance(products, dict):
        raise HTTPException(status_code=400, detail="products must be an object")
    normalised: dict[str, Any] = {}
    health: dict[str, str] = {}
    for key, value in products.items():
        component = _normalise_product(key)
        if component not in {"launcher", "hub", "analysis", "viewer", "scout"}:
            continue
        info = value if isinstance(value, dict) else {}
        normalised[component] = {
            "installed": bool(info.get("installed", False)),
            "version": str(info.get("version") or ""),
            "running": bool(info.get("running", False)),
        }
        health[component] = str(info.get("health") or ("healthy" if info.get("installed") else "not_installed"))
    device.installed_products_json = json.dumps(normalised, sort_keys=True)
    device.product_health_json = json.dumps(health, sort_keys=True)
    live_status = payload.get("live_status", {})
    if isinstance(live_status, dict):
        safe_live = {
            "hostname": str(live_status.get("hostname") or "")[:160],
            "platform": str(live_status.get("platform") or "")[:240],
            "python": str(live_status.get("python") or "")[:80],
            "uptime_seconds": max(0, int(live_status.get("uptime_seconds") or 0)),
            "memory_percent": max(0.0, min(100.0, float(live_status.get("memory_percent") or 0))),
            "disk_percent": max(0.0, min(100.0, float(live_status.get("disk_percent") or 0))),
            "processes": live_status.get("processes") if isinstance(live_status.get("processes"), dict) else {},
            "reported_at": datetime.now(timezone.utc).isoformat(),
        }
        device.live_status_json = json.dumps(safe_live, sort_keys=True)
    device.last_validated_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        admin_user_id=user.id, action="product_inventory_reported", category="device",
        target_type="device", target_id=device.id, target_label=device.device_name or device.device_id,
        details=f"{user.email} reported {len(normalised)} product inventory entries.",
    ))
    db.commit()
    return {
        "status": "recorded",
        "licensed_products": sorted(_licensed_components(user, device) - {"launcher"}),
        "products": normalised,
    }


@router.get("/releases/{release_id}")
def release_metadata(
    release_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    release = db.get(Release, release_id)
    if release is None or release.status != "published":
        raise HTTPException(status_code=404, detail="Published release not found.")
    return {"component": release.component, **_release_payload(release, request)}


def _file_chunks(path: Path, start: int, length: int) -> Iterator[bytes]:
    remaining = length
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/packages/{filename}", name="download_package")
def download_package(
    filename: str,
    request: Request,
    range_header: str | None = Header(default=None, alias="Range"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    safe_name = Path(filename).name
    release = db.scalar(
        select(Release).where(Release.package_filename == safe_name, Release.status == "published")
    )
    if release is None:
        raise HTTPException(status_code=404, detail="Published update package not found.")

    candidate = (PACKAGES_DIR / safe_name).resolve()
    packages_root = PACKAGES_DIR.resolve()
    if packages_root not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Update package not found.")

    total = candidate.stat().st_size
    start = 0
    end = total - 1
    response_status = status.HTTP_200_OK
    if range_header:
        try:
            unit, value = range_header.split("=", 1)
            if unit.strip().lower() != "bytes" or "," in value:
                raise ValueError
            first, last = value.split("-", 1)
            start = int(first) if first else 0
            end = int(last) if last else total - 1
            if start < 0 or start >= total or end < start:
                raise ValueError
            end = min(end, total - 1)
            response_status = status.HTTP_206_PARTIAL_CONTENT
        except ValueError as exc:
            raise HTTPException(status_code=416, detail="Invalid byte range.", headers={"Content-Range": f"bytes */{total}"}) from exc

    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "ETag": f'"{release.package_sha256}"',
        "X-FAST-Release-ID": str(release.id),
    }
    if response_status == status.HTTP_206_PARTIAL_CONTENT:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"

    db.add(AuditLog(
        admin_user_id=user.id,
        action="download_started",
        category="release",
        target_type="release",
        target_id=release.id,
        target_label=f"{release.component} {release.version}",
        details=f"Update package download requested by {user.email}; bytes {start}-{end} of {total}.",
    ))
    db.commit()

    return StreamingResponse(
        _file_chunks(candidate, start, length),
        status_code=response_status,
        media_type="application/zip",
        headers=headers,
    )


@router.post("/downloads/{release_id}/complete")
def download_complete(
    release_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record that Launcher completed and verified a package download."""
    release = db.get(Release, release_id)
    if release is None or release.status != "published":
        raise HTTPException(status_code=404, detail="Published release not found.")
    bytes_downloaded = int(payload.get("bytes_downloaded", 0) or 0)
    db.add(AuditLog(
        admin_user_id=user.id,
        action="download_verified",
        category="release",
        target_type="release",
        target_id=release.id,
        target_label=f"{release.component} {release.version}",
        details=f"Launcher verified the downloaded package for {user.email}; {bytes_downloaded} bytes.",
    ))
    db.commit()
    return {
        "status": "verified",
        "release_id": release.id,
        "component": release.component,
        "version": release.version,
        "bytes_downloaded": bytes_downloaded,
    }


@router.get("/releases/{release_id}/installer-manifest")
def installer_manifest(
    release_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return immutable package data used to construct a local install plan."""
    release = db.get(Release, release_id)
    if release is None or release.status != "published":
        raise HTTPException(status_code=404, detail="Published release not found.")
    return {
        "schema_version": 1,
        "release_id": release.id,
        "component": release.component,
        "version": release.version,
        "channel": release.channel,
        "package": release.package_filename,
        "sha256": release.package_sha256,
        "size": int(release.package_size or 0),
        "status": "ready_for_launcher",
    }

@router.post("/installs/{release_id}/complete")
def install_complete(
    release_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record the result of a Launcher-managed installation."""
    release = db.get(Release, release_id)
    if release is None or release.status != "published":
        raise HTTPException(status_code=404, detail="Published release not found.")
    success = bool(payload.get("success", False))
    component = str(payload.get("component", release.component))
    version = str(payload.get("version", release.version))
    detail = str(payload.get("detail", ""))[:1000]
    db.add(AuditLog(
        admin_user_id=user.id,
        action="install_succeeded" if success else "install_failed",
        category="release",
        target_type="release",
        target_id=release.id,
        target_label=f"{component} {version}",
        details=f"Launcher installation {'succeeded' if success else 'failed'} for {user.email}. {detail}".strip(),
    ))
    db.commit()
    return {"status": "installed" if success else "failed", "release_id": release.id,
            "component": component, "version": version}

@router.get("/launcher/latest")
def latest_launcher_release(
    channel: str = Query("stable"),
    device_id: str = Query(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the latest published FAST Launcher release for self-update clients."""
    channel = channel.lower().strip()
    if channel not in CHANNELS:
        raise HTTPException(status_code=400, detail="Unknown release channel.")
    release = db.scalar(
        select(Release)
        .where(
            Release.component == "launcher",
            Release.channel == channel,
            Release.status == "published",
            Release.package_filename.is_not(None),
            Release.package_sha256.is_not(None),
        )
        .order_by(Release.published_at.desc(), Release.id.desc())
    )
    if release is None:
        return {"schema_version": 1, "channel": channel, "release": None}
    return {"schema_version": 1, "channel": channel, "release": _release_payload(release)}


@router.post("/launcher/{release_id}/self-update-complete")
def launcher_self_update_complete(
    release_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record the external FAST Updater result after Launcher restarts."""
    release = db.get(Release, release_id)
    if release is None or release.component != "launcher" or release.status != "published":
        raise HTTPException(status_code=404, detail="Published Launcher release not found.")
    success = bool(payload.get("success", False))
    detail = str(payload.get("detail", ""))[:1000]
    db.add(AuditLog(
        admin_user_id=user.id,
        action="launcher_self_update_succeeded" if success else "launcher_self_update_failed",
        category="release",
        target_type="release",
        target_id=release.id,
        target_label=f"launcher {release.version}",
        details=f"FAST Updater self-update {'succeeded' if success else 'failed'} for {user.email}. {detail}".strip(),
    ))
    db.commit()
    return {"status": "installed" if success else "failed", "release_id": release.id, "version": release.version}


@router.post("/telemetry/{release_id}")
def update_telemetry(
    release_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record a non-blocking Launcher update lifecycle event."""
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found.")
    event = str(payload.get("event", "")).strip().lower()[:80]
    allowed = {
        "offered", "deferred", "skipped", "download_started", "download_completed",
        "verification_passed", "verification_failed", "install_started", "install_completed",
        "install_failed", "restart_succeeded", "rollback_triggered", "mandatory_blocked",
    }
    if event not in allowed:
        raise HTTPException(status_code=400, detail="Unknown update telemetry event.")
    component = str(payload.get("component", release.component))[:40]
    version = str(payload.get("version", release.version))[:40]
    detail = str(payload.get("detail", ""))[:1000]
    device_id = str(payload.get("device_id", ""))[:160]
    details = f"{user.email}; component={component}; version={version}"
    if device_id:
        details += f"; device={device_id}"
    if detail:
        details += f"; {detail}"
    db.add(AuditLog(
        admin_user_id=user.id, action=f"update_{event}", category="release",
        target_type="release", target_id=release.id,
        target_label=f"{release.component} {release.version}", details=details,
    ))
    db.commit()
    return {"status": "recorded", "event": event, "release_id": release.id}


@router.post("/device-telemetry")
def device_telemetry(
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist Launcher/device health independently of a specific release."""
    device_id = str(payload.get("device_id", "")).strip()[:160]
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required.")
    event = str(payload.get("event", "heartbeat")).strip().lower()[:80]
    allowed = {
        "launcher_started", "heartbeat", "update_check", "update_available",
        "update_deferred", "update_skipped", "download_started", "download_completed",
        "verification_passed", "verification_failed", "install_started",
        "install_completed", "install_failed", "restart_succeeded", "rollback_triggered",
    }
    if event not in allowed:
        raise HTTPException(status_code=400, detail="Unknown device telemetry event.")
    activation = db.scalar(
        select(DeviceActivation)
        .where(DeviceActivation.device_id == device_id)
        .order_by(DeviceActivation.active.desc(), DeviceActivation.last_validated_at.desc())
    )
    if activation is None:
        # Remote-command polling is a background capability check. A Launcher can
        # legitimately be signed in before this machine has an active device
        # activation (or immediately after an administrator deactivates it).
        # Treat that state as an empty queue instead of a 404 so the periodic
        # poll stays quiet and does not look like a Cloud/Launcher route mismatch.
        return {"commands": [], "device_registered": False}

    version = str(payload.get("installed_version", "")).strip()[:40]
    channel = str(payload.get("channel", "")).strip().lower()[:20]
    pending = str(payload.get("pending_update_version", "")).strip()[:40]
    detail = str(payload.get("detail", "")).strip()[:1000]
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    activation.last_validated_at = now
    if version:
        activation.installed_version = version
    if channel:
        activation.update_channel = "alpha" if channel == "internal" else channel
    activation.last_telemetry_event = event
    if pending:
        activation.pending_update_version = pending
    if event in {"install_completed", "restart_succeeded"}:
        activation.last_update_at = now
        activation.update_health = "healthy"
        activation.pending_update_version = None
    elif event in {"verification_failed", "install_failed", "rollback_triggered"}:
        activation.update_health = "attention"
    elif event == "update_available":
        activation.update_health = "update available"
    elif not activation.update_health:
        activation.update_health = "healthy"

    description = f"Launcher {version or activation.installed_version or 'unknown'}; channel={activation.update_channel or 'unknown'}"
    if pending:
        description += f"; pending={pending}"
    if detail:
        description += f"; {detail}"
    db.add(DeviceAuditLog(
        device_activation_id=activation.id,
        admin_user_id=user.id,
        action=event,
        details=description,
    ))
    db.add(AuditLog(
        admin_user_id=user.id, action=f"device_{event}", category="device",
        target_type="device", target_id=activation.id,
        target_label=activation.device_name or activation.device_id, details=description,
    ))
    db.commit()
    return {
        "status": "recorded", "event": event, "device_id": device_id,
        "installed_version": activation.installed_version,
        "channel": activation.update_channel,
        "update_health": activation.update_health,
    }


@router.post("/device-commands/poll")
def poll_device_commands(
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    device_id = str(payload.get("device_id", "")).strip()[:160]
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required.")
    activation = db.scalar(select(DeviceActivation).where(
        DeviceActivation.device_id == device_id, DeviceActivation.active.is_(True)
    ))
    if activation is None:
        raise HTTPException(status_code=404, detail="Registered device not found.")
    if not _user_can_access_device(db, user, activation):
        raise HTTPException(status_code=403, detail="Device is not assigned to this account.")
    now = datetime.now(timezone.utc)
    commands = db.scalars(
        select(RemoteCommand).where(
            RemoteCommand.device_activation_id == activation.id,
            RemoteCommand.status == "pending",
        ).order_by(RemoteCommand.created_at.asc()).limit(10)
    ).all()
    result = []
    for command in commands:
        command.status = "claimed"
        command.claimed_at = now
        try:
            command_payload = json.loads(command.payload_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            command_payload = {}
        result.append({"id": command.id, "command": command.command, "payload": command_payload})
    activation.last_validated_at = now
    db.commit()
    return {"commands": result}


@router.post("/device-commands/{command_id}/result")
def report_device_command_result(
    command_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    command = db.get(RemoteCommand, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Remote command not found.")
    activation = db.get(DeviceActivation, command.device_activation_id)
    if activation is None:
        raise HTTPException(status_code=404, detail="Registered device not found.")
    device_id = str(payload.get("device_id", "")).strip()[:160]
    if device_id != activation.device_id:
        raise HTTPException(status_code=403, detail="Command does not belong to this device.")
    if not _user_can_access_device(db, user, activation):
        raise HTTPException(status_code=403, detail="Device is not assigned to this account.")
    status_value = str(payload.get("status", "failed")).strip().lower()
    command.status = "completed" if status_value == "completed" else "failed"
    command.result = str(payload.get("result", ""))[:2000]
    command.completed_at = datetime.now(timezone.utc)
    db.add(DeviceAuditLog(
        device_activation_id=activation.id, admin_user_id=user.id,
        action=f"remote_{command.command}_{command.status}", details=command.result,
    ))
    db.commit()
    return {"status": command.status, "command_id": command.id}
