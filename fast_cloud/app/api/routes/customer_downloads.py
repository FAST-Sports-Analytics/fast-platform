from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.storage import release_packages_dir
from app.db.session import get_db
from app.models import AuditLog, Release, User

router = APIRouter(tags=["Customer Downloads"])
ROOT = release_packages_dir() / "customer_downloads"
ROOT.mkdir(parents=True, exist_ok=True)
METADATA = ROOT / "launcher.json"
MAX_INSTALLER_BYTES = 2 * 1024 * 1024 * 1024


def _canonical_channel(value: str) -> str:
    value = str(value or "").strip().lower()
    return "internal" if value in {"alpha", "internal"} else value


def _read_metadata() -> dict:
    try:
        payload = json.loads(METADATA.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _published_release(db: Session, metadata: dict) -> Release | None:
    version = str(metadata.get("version") or "").strip()
    channel = _canonical_channel(metadata.get("channel") or "")
    ring = str(metadata.get("deployment_ring") or "").strip().lower()
    if not version or not channel or ring != "production":
        return None
    aliases = {channel}
    if channel == "internal":
        aliases.add("alpha")
    return db.scalar(
        select(Release).where(
            func.lower(Release.component) == "launcher",
            Release.version == version,
            func.lower(Release.channel).in_(aliases),
            func.lower(Release.deployment_ring) == "production",
            func.lower(Release.status) == "published",
        )
        .order_by(Release.published_at.desc(), Release.id.desc())
    )


@router.post("/api/customer-downloads/launcher/upload")
async def upload_launcher_installer(
    version: str = Form(...),
    channel: str = Form(...),
    deployment_ring: str = Form(...),
    expected_sha256: str = Form(...),
    installer: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    version = version.strip()
    channel = _canonical_channel(channel)
    deployment_ring = deployment_ring.strip().lower()
    if not version:
        raise HTTPException(status_code=400, detail="Launcher version is required.")
    if channel not in {"internal", "beta", "stable"}:
        raise HTTPException(status_code=400, detail="Invalid Launcher channel.")
    if deployment_ring not in {"development", "internal", "beta", "pilot", "production"}:
        raise HTTPException(status_code=400, detail="Invalid deployment ring.")
    filename = Path(installer.filename or "").name
    if not filename.lower().endswith(".exe"):
        raise HTTPException(status_code=400, detail="Customer Launcher installer must be an EXE.")

    ROOT.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".fast-launcher-", suffix=".exe", dir=ROOT, delete=False) as output:
            temp_path = Path(output.name)
            while chunk := await installer.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_INSTALLER_BYTES:
                    raise ValueError("Customer Launcher installer exceeds the 2 GB limit.")
                digest.update(chunk)
                output.write(chunk)
        actual = digest.hexdigest()
        if not expected_sha256.strip() or actual.lower() != expected_sha256.strip().lower():
            raise ValueError("Customer Launcher installer checksum does not match Builder.")
        final_name = f"FAST_Launcher_Setup_{version}_Windows_x64.exe"
        final_path = ROOT / final_name
        if final_path.exists():
            final_path.unlink()
        temp_path.replace(final_path)
        temp_path = None

        metadata = {
            "schema_version": 1,
            "product": "FAST Launcher",
            "version": version,
            "platform": "Windows x64",
            "channel": channel,
            "deployment_ring": deployment_ring,
            "filename": final_name,
            "sha256": actual,
            "size_bytes": size,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary_metadata = METADATA.with_suffix(".tmp")
        temporary_metadata.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        temporary_metadata.replace(METADATA)

        db.add(AuditLog(
            admin_user_id=admin.id,
            action="customer_launcher_installer_uploaded",
            category="release",
            target_type="launcher_installer",
            target_label=f"FAST Launcher {version}",
            details=f"Customer Windows installer uploaded for {deployment_ring} ({size} bytes; SHA-256 {actual}).",
        ))
        db.commit()
        return {"status": "uploaded", "installer": metadata}
    except (OSError, ValueError) as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await installer.close()


@router.get("/api/v1/customer-downloads/launcher/latest")
def latest_launcher_installer(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    metadata = _read_metadata()
    release = _published_release(db, metadata)
    filename = Path(str(metadata.get("filename") or "")).name
    installer_path = ROOT / filename if filename else Path("")
    if release is None or not filename or not installer_path.is_file():
        return {"schema_version": 1, "installer": None}
    payload = dict(metadata)
    payload["release_id"] = release.id
    payload["download_url"] = str(request.url_for("download_customer_launcher"))
    return {"schema_version": 1, "installer": payload}


@router.get("/api/v1/customer-downloads/launcher/file", name="download_customer_launcher")
def download_launcher_installer(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    metadata = _read_metadata()
    release = _published_release(db, metadata)
    filename = Path(str(metadata.get("filename") or "")).name
    installer_path = ROOT / filename if filename else Path("")
    if release is None or not filename or not installer_path.is_file():
        raise HTTPException(status_code=404, detail="FAST Launcher installer is not currently available.")
    db.add(AuditLog(
        admin_user_id=user.id,
        action="customer_launcher_downloaded",
        category="release",
        target_type="launcher_installer",
        target_id=release.id,
        target_label=f"FAST Launcher {metadata.get('version')}",
        details=f"{user.email} downloaded the Windows FAST Launcher installer.",
    ))
    db.commit()
    return FileResponse(
        installer_path,
        media_type="application/vnd.microsoft.portable-executable",
        filename=filename,
        headers={
            "X-FAST-Version": str(metadata.get("version") or ""),
            "X-FAST-SHA256": str(metadata.get("sha256") or ""),
        },
    )
