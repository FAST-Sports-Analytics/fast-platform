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

router = APIRouter(prefix="/admin/releases", tags=["Admin Releases"])
PACKAGES_DIR = release_packages_dir()
CHANNELS = {"stable", "beta", "alpha", "internal"}
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024


def canonical_channel(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return "internal" if normalized in {"alpha", "internal"} else normalized


def _clean(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._") or "release"


def _destination_name(component: str, version: str, channel: str) -> str:
    return f"fast-{_clean(component)}-{_clean(version)}-{_clean(channel)}.zip"


def _validate_package(path: Path, component: str, version: str, channel: str) -> dict:
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if not members:
                raise ValueError("The ZIP package is empty.")
            root = Path("payload").resolve()
            for member in members:
                target = (root / member.filename.replace("\\", "/")).resolve()
                if target != root and root not in target.parents:
                    raise ValueError("The ZIP package contains an unsafe path.")
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"The ZIP package is corrupt near {bad_member}.")
            metadata_names = [name for name in archive.namelist() if name.endswith("FAST_RELEASE.json")]
            if not metadata_names:
                raise ValueError("FAST_RELEASE.json is missing from the package.")
            metadata = json.loads(archive.read(metadata_names[-1]).decode("utf-8"))
    except (BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("The uploaded file is not a valid FAST release package.") from exc

    if str(metadata.get("component", "")).strip().lower() != component:
        raise ValueError("Package component does not match the release request.")
    if str(metadata.get("version", "")).strip() != version:
        raise ValueError("Package version does not match the release request.")
    if canonical_channel(metadata.get("channel", "")) != canonical_channel(channel):
        raise ValueError("Package channel does not match the release request.")
    return metadata


@router.get("")
def list_releases(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    items = db.scalars(select(Release).order_by(Release.created_at.desc())).all()
    return {
        "releases": [
            {
                "id": item.id,
                "component": item.component,
                "version": item.version,
                "channel": item.channel,
                "status": item.status,
                "package_filename": item.package_filename,
                "package_sha256": item.package_sha256,
                "package_size": item.package_size,
                "created_at": item.created_at,
                "published_at": item.published_at,
                "product_target": item.product_target or "all",
                "minimum_launcher_version": item.minimum_launcher_version,
                "deployment_ring": item.deployment_ring,
                "rollout_percentage": int(getattr(item, "rollout_percentage", 100) or 0),
                "rollout_status": getattr(item, "rollout_status", "active") or "active",
                "rollout_notes": getattr(item, "rollout_notes", None),
            }
            for item in items
        ]
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_release(
    component: str = Form(...),
    version: str = Form(...),
    channel: str = Form("internal"),
    release_notes: str = Form(""),
    expected_sha256: str = Form(""),
    package: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    component = component.strip().lower()
    version = version.strip()
    channel = canonical_channel(channel)
    if not component or not version:
        raise HTTPException(status_code=400, detail="Component and version are required.")
    if channel not in CHANNELS:
        raise HTTPException(status_code=400, detail="Unknown release channel.")
    if not (package.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Release package must be a ZIP file.")

    existing = db.scalar(select(Release).where(
        Release.component == component,
        Release.version == version,
        Release.channel == channel,
    ))
    if existing and existing.status != "draft":
        raise HTTPException(status_code=409, detail="This release is already published and cannot be replaced.")

    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".fast-upload-", suffix=".zip", dir=PACKAGES_DIR, delete=False) as output:
            temporary_path = Path(output.name)
            while chunk := await package.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_PACKAGE_BYTES:
                    raise ValueError("The release package exceeds the 2 GB upload limit.")
                digest.update(chunk)
                output.write(chunk)
        actual_sha256 = digest.hexdigest()
        if expected_sha256 and actual_sha256.lower() != expected_sha256.strip().lower():
            raise ValueError("Package checksum does not match the Builder manifest.")
        _validate_package(temporary_path, component, version, channel)

        filename = _destination_name(component, version, channel)
        final_path = PACKAGES_DIR / filename
        temporary_path.replace(final_path)
        temporary_path = None
    except (OSError, ValueError) as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await package.close()

    item = existing or Release(
        component=component,
        version=version,
        channel=channel,
        status="draft",
        created_by_user_id=admin.id,
    )
    if existing is None:
        db.add(item)
        db.flush()
    elif item.package_filename and item.package_filename != filename:
        (PACKAGES_DIR / Path(item.package_filename).name).unlink(missing_ok=True)

    item.release_notes = release_notes.strip() or None
    item.package_filename = filename
    item.package_sha256 = actual_sha256
    item.package_size = size
    item.updated_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        admin_user_id=admin.id,
        action="uploaded",
        category="release",
        target_type="release",
        target_id=item.id,
        target_label=f"{component} {version}",
        details=f"FAST Builder uploaded {filename} to the {channel} channel as a draft.",
    ))
    db.commit()
    db.refresh(item)
    return {
        "message": "Release package uploaded and registered as a draft.",
        "release": {
            "id": item.id,
            "component": item.component,
            "version": item.version,
            "channel": item.channel,
            "status": item.status,
            "package_filename": item.package_filename,
            "package_sha256": item.package_sha256,
            "package_size": item.package_size,
        },
    }
