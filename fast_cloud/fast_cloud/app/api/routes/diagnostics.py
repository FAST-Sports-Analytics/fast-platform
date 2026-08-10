from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import CrashReport, DeviceActivation, User

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


@router.post("/crashes")
def submit_crash(
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    component = _text(payload.get("component") or "launcher", 40).lower()
    version = _text(payload.get("version"), 40)
    exception_type = _text(payload.get("exception_type") or "Exception", 160)
    message = _text(payload.get("message"), 2000)
    traceback_text = _text(payload.get("traceback"), 30000)
    device_id = _text(payload.get("device_id"), 160)
    channel = _text(payload.get("channel"), 30).lower()
    deployment_ring = _text(payload.get("deployment_ring"), 30).lower()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    if not traceback_text and not message:
        raise HTTPException(status_code=400, detail="Crash report must include a message or traceback.")

    fingerprint_source = "\n".join((component, exception_type, message, traceback_text.splitlines()[-1] if traceback_text else ""))
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8", errors="replace")).hexdigest()

    device = None
    if device_id:
        device = db.scalar(
            select(DeviceActivation)
            .where(DeviceActivation.device_id == device_id)
            .order_by(DeviceActivation.id.desc())
        )

    report = db.scalar(select(CrashReport).where(CrashReport.fingerprint == fingerprint))
    now = datetime.now(timezone.utc)
    if report is None:
        report = CrashReport(
            fingerprint=fingerprint,
            component=component,
            version=version or None,
            exception_type=exception_type,
            message=message or None,
            traceback=traceback_text or None,
            status="open",
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(report)
    else:
        report.occurrence_count = int(report.occurrence_count or 0) + 1
        report.last_seen_at = now
        report.version = version or report.version
        report.message = message or report.message
        report.traceback = traceback_text or report.traceback

    report.user_id = user.id
    report.organisation_id = user.organisation_id
    report.device_activation_id = device.id if device else None
    report.device_id = device_id or None
    report.channel = channel or None
    report.deployment_ring = deployment_ring or None
    report.context_json = json.dumps(context, ensure_ascii=False, default=str)[:20000]
    db.commit()
    db.refresh(report)
    return {"status": "recorded", "incident_id": report.id, "fingerprint": fingerprint, "occurrences": report.occurrence_count}
