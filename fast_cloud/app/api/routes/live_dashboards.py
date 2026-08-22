from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import LiveDashboardSnapshot, User

router = APIRouter(prefix="/live-dashboards", tags=["Live dashboards"])


class DashboardSnapshotRequest(BaseModel):
    sport_id: str = "football"
    fixture_name: str = ""
    home_team: str = "Home"
    away_team: str = "Away"
    image_png_base64: str = Field(min_length=1, max_length=12_000_000)
    page_name: str = "Overview"
    dashboard_name: str = "Live Match Dashboard"
    match_clock_ms: int = 0


def _org_id(user: User) -> int:
    if user.organisation_id is None:
        raise HTTPException(status_code=403, detail="Organisation membership required")
    return int(user.organisation_id)


@router.put("/{match_id}")
def publish_dashboard(match_id: str, payload: DashboardSnapshotRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _org_id(user)
    key = str(match_id).strip()
    if not key:
        raise HTTPException(status_code=400, detail="match_id is required")
    row = db.query(LiveDashboardSnapshot).filter(
        LiveDashboardSnapshot.organisation_id == organisation_id,
        LiveDashboardSnapshot.match_id == key,
    ).one_or_none()
    if row is None:
        row = LiveDashboardSnapshot(organisation_id=organisation_id, match_id=key)
        db.add(row)
    row.payload_json = json.dumps(payload.model_dump(), separators=(",", ":"))
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "match_id": key, "updated_at": row.updated_at.isoformat()}


@router.get("/{match_id}")
def read_dashboard(match_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _org_id(user)
    row = db.query(LiveDashboardSnapshot).filter(
        LiveDashboardSnapshot.organisation_id == organisation_id,
        LiveDashboardSnapshot.match_id == str(match_id).strip(),
    ).one_or_none()
    if row is None:
        return {"available": False, "match_id": str(match_id)}
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {"available": True, "match_id": row.match_id, "updated_at": row.updated_at.isoformat() if row.updated_at else None, "snapshot": payload}
