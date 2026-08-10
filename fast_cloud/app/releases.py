from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.storage import release_packages_dir
from app.db.session import get_db
from app.models import AuditLog, Release, User

router = APIRouter(prefix="/api/releases", tags=["Release Uploads"])
PACKAGES_DIR = release_packages_dir()
CHANNELS = {"stable", "beta", "alpha", "internal"}
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024


def canonical_channel(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return "internal" if normalized in {"alpha", "internal"} else normalized


def clean_release_value(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._") or "release"


def destination_name(component: str, version: str, channel: str) -> str:
    return f"fast-{clean_release_value(component)}-{clean_release_value(version)}-{clean_release_value(channel)}.zip"


def validate_release_package(path: Path, component: str | None = None, version: str | None = None, channel: str | None = None) -> dict:
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if not members: raise ValueError("The ZIP package is empty.")
            root = Path("payload").resolve()
            for member in members:
                target = (root / member.filename.replace("\\", "/")).resolve()
                if target != root and root not in target.parents:
                    raise ValueError(f"The ZIP package contains an unsafe path: {member.filename}")
            bad_member = archive.testzip()
            if bad_member: raise ValueError(f"The ZIP package is corrupt near {bad_member}.")
            metadata_names = [name for name in archive.namelist() if name.endswith("FAST_RELEASE.json")]
            if not metadata_names: raise ValueError("FAST_RELEASE.json is missing from the package.")
            metadata = json.loads(archive.read(metadata_names[-1]).decode("utf-8"))
    except (BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("The uploaded file is not a valid FAST release package.") from exc
    if component is not None and str(metadata.get("component", "")).strip().lower() != component:
        raise ValueError("Package component does not match the release request.")
    if version is not None and str(metadata.get("version", "")).strip() != version:
        raise ValueError("Package version does not match the release request.")
    if channel is not None and canonical_channel(metadata.get("channel", "")) != canonical_channel(channel):
        raise ValueError("Package channel does not match the release request.")
    return metadata


async def receive_release_upload(
    *, component: str, version: str, channel: str, source_channel: str, deployment_ring: str, release_notes: str,
    expected_sha256: str, manifest_json: str, publish_immediately: bool, duplicate_action: str, initial_rollout_percentage: int, rollout_notes: str, package: UploadFile,
    admin: User, db: Session,
) -> dict:
    component = component.strip().lower(); version = version.strip(); channel = canonical_channel(channel); source_channel = canonical_channel(source_channel or channel)
    duplicate_action = duplicate_action.strip().lower()
    deployment_ring = deployment_ring.strip().lower()
    initial_rollout_percentage = max(0, min(100, int(initial_rollout_percentage or 0)))
    if not component: raise HTTPException(status_code=400, detail="Component is required.")
    if not version: raise HTTPException(status_code=400, detail="Version is required.")
    if channel not in CHANNELS: raise HTTPException(status_code=400, detail="Release channel must be internal, beta, or stable.")
    if source_channel not in CHANNELS: raise HTTPException(status_code=400, detail="Source package channel must be internal, beta, or stable.")
    if deployment_ring not in {"development", "internal", "beta", "pilot", "production"}: raise HTTPException(status_code=400, detail="Invalid deployment ring.")
    if duplicate_action not in {"reject", "replace_draft"}: raise HTTPException(status_code=400, detail="Unsupported duplicate action.")
    if not (package.filename or "").lower().endswith(".zip"): raise HTTPException(status_code=400, detail="Release package must be a ZIP file.")
    try:
        manifest = json.loads(manifest_json) if manifest_json.strip() else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Builder manifest is not valid JSON.") from exc
    for key, expected in (("component", component), ("version", version)):
        if manifest and str(manifest.get(key, "")).strip().lower() != expected.lower():
            raise HTTPException(status_code=400, detail=f"Builder manifest {key} does not match the upload request.")
    if manifest and canonical_channel(manifest.get("channel", "")) != source_channel:
        raise HTTPException(status_code=400, detail="Builder manifest channel does not match the upload request.")

    existing = db.scalar(select(Release).where(Release.component == component, Release.version == version, Release.channel == channel))
    replacing = existing is not None
    if existing and duplicate_action != "replace_draft":
        raise HTTPException(status_code=409, detail=f"{component} {version} already exists in the {channel} channel. Choose Replace existing draft or use a new version.")
    if existing and existing.status != "draft":
        raise HTTPException(status_code=409, detail=f"{component} {version} is already published or archived and cannot be replaced.")

    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(); size = 0; temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".fast-upload-", suffix=".zip", dir=PACKAGES_DIR, delete=False) as output:
            temporary_path = Path(output.name)
            while chunk := await package.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_PACKAGE_BYTES: raise ValueError("The release package exceeds the 2 GB upload limit.")
                digest.update(chunk); output.write(chunk)
        actual_sha256 = digest.hexdigest()
        if not expected_sha256.strip(): raise ValueError("Expected SHA-256 is required.")
        if actual_sha256.lower() != expected_sha256.strip().lower(): raise ValueError("Package checksum does not match the Builder manifest.")
        if manifest.get("sha256") and str(manifest["sha256"]).lower() != actual_sha256.lower(): raise ValueError("Package checksum does not match the received manifest.")
        metadata = validate_release_package(temporary_path, component, version, source_channel)
        filename = destination_name(component, version, channel)
        final_path = PACKAGES_DIR / filename
        if final_path.exists():
            if replacing: final_path.unlink()
            else: raise ValueError(f"A package file named {filename} already exists.")
        temporary_path.replace(final_path); temporary_path = None
    except (OSError, ValueError) as exc:
        if temporary_path is not None: temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await package.close()

    now = datetime.now(timezone.utc)
    if existing:
        item = existing
        item.release_notes = release_notes.strip() or None
        item.deployment_ring = deployment_ring
        item.package_filename = filename
        item.package_sha256 = actual_sha256
        item.package_size = size
        item.rollout_percentage = initial_rollout_percentage
        item.rollout_status = "active"
        item.rollout_notes = rollout_notes.strip() or None
        item.updated_at = now
        action = "replaced"
    else:
        item = Release(component=component, version=version, channel=channel, status="draft", release_notes=release_notes.strip() or None,
                       deployment_ring=deployment_ring, rollout_percentage=initial_rollout_percentage, rollout_status="active", rollout_notes=rollout_notes.strip() or None, package_filename=filename, package_sha256=actual_sha256, package_size=size, created_by_user_id=admin.id,
                       updated_at=now)
        db.add(item); db.flush()
        action = "uploaded"
    if publish_immediately:
        item.status = "published"
        item.published_at = now
    else:
        item.status = "draft"
        item.published_at = None
    db.add(AuditLog(admin_user_id=admin.id, action=action, category="release", target_type="release", target_id=item.id,
                    target_label=f"{component} {version}", details=f"FAST Builder {action} {filename} ({size} bytes, SHA-256 {actual_sha256}) to {channel} as {item.status}."))
    db.commit(); db.refresh(item)
    return {"message": f"Release package {action} and registered as {item.status}.", "release": {
        "id": item.id, "component": item.component, "version": item.version, "channel": item.channel, "status": item.status,
        "package_filename": item.package_filename, "package_sha256": item.package_sha256, "package_size": item.package_size,
        "metadata": metadata,
    }}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_release(
    component: str = Form(...), version: str = Form(...), channel: str = Form("internal"), source_channel: str = Form("internal"),
    deployment_ring: str = Form("development"), release_notes: str = Form(""), expected_sha256: str = Form(...), manifest_json: str = Form("{}"),
    publish_immediately: bool = Form(False), duplicate_action: str = Form("reject"), initial_rollout_percentage: int = Form(100), rollout_notes: str = Form(""),
    package: UploadFile = File(...), admin: User = Depends(require_admin), db: Session = Depends(get_db),
) -> dict:
    return await receive_release_upload(component=component, version=version, channel=channel, source_channel=source_channel, deployment_ring=deployment_ring, release_notes=release_notes,
                                        expected_sha256=expected_sha256, manifest_json=manifest_json, publish_immediately=publish_immediately, duplicate_action=duplicate_action, initial_rollout_percentage=initial_rollout_percentage, rollout_notes=rollout_notes,
                                        package=package, admin=admin, db=db)
