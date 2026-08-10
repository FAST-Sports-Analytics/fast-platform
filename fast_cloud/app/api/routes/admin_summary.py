from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import Club, DeviceActivation, Licence, Organisation, User

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/summary")
def administration_summary(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    licences = db.scalars(select(Licence)).all()
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "clubs": db.scalar(select(func.count(Club.id))) or 0,
        "organisations": db.scalar(select(func.count(Organisation.id))) or 0,
        "licences": len(licences),
        "active_licences": sum(1 for item in licences if item.status == "active"),
        "expired_licences": sum(1 for item in licences if item.status == "expired"),
        "active_devices": db.scalar(
            select(func.count(DeviceActivation.id)).where(DeviceActivation.active.is_(True))
        ) or 0,
        "cloud_status": "Online",
    }
