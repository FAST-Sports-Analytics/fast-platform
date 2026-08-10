from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.security import generate_licence_code, hash_licence_code, normalise_licence_code
from app.core.entitlements import filter_products, filter_sports, licence_is_current
from app.core.subscription_access import organisation_subscription_access
from app.db.session import get_db
from app.models import Club, ClubMember, DeviceActivation, DeviceAuditLog, Licence, User
from app.schemas.licence import (
    ActivateLicenceRequest,
    CreateLicenceRequest,
    DeactivateDeviceRequest,
    ValidateLicenceRequest,
)

router = APIRouter(prefix="/licences", tags=["Licences"])
admin_router = APIRouter(prefix="/admin/licences", tags=["Admin Licences"])


def current_licence_for_user(db: Session, user: User) -> Licence | None:
    """Resolve a licence through direct ownership, club membership, or organisation."""
    member_club_ids = select(ClubMember.club_id).where(ClubMember.user_id == user.id)
    club_access = Licence.club_id.in_(member_club_ids)

    # Only add organisation-club access when the user actually belongs to one.
    # A normal Python bool cannot be combined with a SQLAlchemy expression using ``&``.
    if user.organisation_id is not None:
        organisation_club_ids = select(Club.id).where(
            Club.organisation_id == user.organisation_id
        )
        club_access = club_access | Licence.club_id.in_(organisation_club_ids)

    return db.scalar(
        select(Licence)
        .where(
            Licence.status == "active",
            ((Licence.owner_type == "individual") & (Licence.user_id == user.id))
            | ((Licence.owner_type == "club") & club_access),
        )
        .order_by(Licence.id.desc())
    )



def access_role_for_licence(db: Session, user: User, licence: Licence) -> str:
    if bool(user.is_admin and user.organisation_id is None):
        return "administrator"
    if getattr(licence, "owner_type", "individual") == "club" and getattr(licence, "club_id", None):
        membership = db.scalar(select(ClubMember).where(
            ClubMember.club_id == licence.club_id,
            ClubMember.user_id == user.id,
        ))
        membership_role = str(getattr(membership, "role", "") or "").strip().lower()
        if membership_role in {"administrator", "analyst", "coach", "scout"}:
            return membership_role
    return str(user.role or "analyst").strip().lower()

def ensure_current(licence: Licence) -> None:
    now = datetime.now(timezone.utc)
    expiry = licence.expires_at
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry and expiry <= now:
        licence.status = "expired"
        raise HTTPException(status_code=403, detail="Licence has expired")
    if licence.status in {"suspended", "revoked", "expired"}:
        raise HTTPException(status_code=403, detail=f"Licence is {licence.status}")


def organisation_payload(licence: Licence) -> dict | None:
    club = getattr(licence, "club", None)
    organisation = getattr(club, "organisation", None) if club else None
    if not organisation:
        return None
    try:
        sports = json.loads(getattr(organisation, "sports_json", "[]") or "[]")
    except (TypeError, ValueError):
        sports = []
    seats_used = sum(len(item.members) for item in organisation.clubs)
    return {
        "id": organisation.id,
        "name": organisation.name,
        "contact_name": organisation.contact_name,
        "contact_email": organisation.contact_email,
        "country": organisation.country,
        "subscription_tier": getattr(organisation, "subscription_tier", None) or licence.tier,
        "sports": sports,
        "max_seats": getattr(organisation, "max_seats", 1),
        "seats_used": seats_used,
        "expires_at": getattr(organisation, "expires_at", None),
        "logo_url": getattr(organisation, "logo_url", None),
        "status": organisation.status,
        "club": {"id": club.id, "name": club.name} if club else None,
    }


def serialise(licence: Licence, active_devices: int | None = None) -> dict:
    return {
        "id": licence.id,
        "tier": licence.tier,
        "products": json.loads(licence.products_json),
        "sports": json.loads(licence.sports_json),
        "features": json.loads(getattr(licence, "features_json", "[]") or "[]"),
        "status": licence.status,
        "expires_at": licence.expires_at,
        "max_devices": licence.max_devices,
        "active_devices": active_devices,
        "code_last_four": licence.code_last_four,
        "owner_type": getattr(licence, "owner_type", "individual"),
        "owner_user_id": licence.user_id,
        "owner_club_id": getattr(licence, "club_id", None),
        "max_users": getattr(licence, "max_users", 1),
        "organisation": organisation_payload(licence),
    }


@admin_router.post("")
def create_licence(
    payload: CreateLicenceRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    code = generate_licence_code(payload.tier)
    licence = Licence(
        code_hash=hash_licence_code(code),
        code_last_four=normalise_licence_code(code)[-4:],
        tier=payload.tier,
        products_json=json.dumps(sorted(set(payload.products))),
        sports_json=json.dumps(sorted(set(payload.sports))),
        features_json=json.dumps(sorted(set(payload.features))),
        expires_at=payload.expires_at,
        max_devices=payload.max_devices,
    )
    db.add(licence)
    db.commit()
    db.refresh(licence)
    return {"licence_code": code, "licence": serialise(licence, 0)}


@router.post("/activate")
def activate(
    payload: ActivateLicenceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    licence = db.scalar(select(Licence).where(Licence.code_hash == hash_licence_code(payload.code)))
    if not licence:
        raise HTTPException(status_code=404, detail="Licence code was not found")
    ensure_current(licence)
    subscription_access = organisation_subscription_access(db, user.organisation_id)
    if not subscription_access.allowed:
        raise HTTPException(status_code=403, detail=subscription_access.message)
    if licence.owner_type == "individual":
        if licence.user_id and licence.user_id != user.id:
            raise HTTPException(status_code=409, detail="Licence is assigned to another account")
    else:
        if not licence.club_id:
            raise HTTPException(status_code=409, detail="Club licence must be assigned to a club before activation")
        membership = db.scalar(select(ClubMember).where(
            ClubMember.club_id == licence.club_id,
            ClubMember.user_id == user.id,
        ))
        if not membership:
            club = db.get(Club, licence.club_id)
            if not club or user.organisation_id is None or club.organisation_id != user.organisation_id:
                raise HTTPException(status_code=403, detail="Your account is not a member of the licensed organisation")

    existing = db.scalar(
        select(DeviceActivation).where(
            DeviceActivation.licence_id == licence.id,
            DeviceActivation.device_id == payload.device_id,
        )
    )
    active_count = db.scalar(
        select(func.count(DeviceActivation.id)).where(
            DeviceActivation.licence_id == licence.id,
            DeviceActivation.active.is_(True),
        )
    ) or 0
    if existing and not existing.active:
        # A deactivated device is an explicit administrative decision.  Re-entering
        # the licence code must not let the same machine consume the reclaimed slot.
        raise HTTPException(
            status_code=409,
            detail="This device has been deactivated. Ask your administrator to reactivate it before using FAST applications.",
        )
    if not existing and active_count >= licence.max_devices:
        raise HTTPException(status_code=409, detail="Device activation limit reached")

    if existing:
        existing.device_name = payload.device_name or existing.device_name
        existing.last_validated_at = datetime.now(timezone.utc)
    else:
        activation = DeviceActivation(
            licence_id=licence.id,
            device_id=payload.device_id,
            device_name=payload.device_name,
        )
        db.add(activation)
        db.flush()
        db.add(DeviceAuditLog(
            device_activation_id=activation.id,
            admin_user_id=user.id,
            action="activated",
            details=f"{payload.device_name or payload.device_id} activated from FAST Launcher.",
        ))
        active_count += 1

    if licence.owner_type == "individual":
        licence.user_id = user.id
    licence.status = "active"
    licence.activated_at = licence.activated_at or datetime.now(timezone.utc)
    db.commit()
    return {"message": "Licence activated", "licence": serialise(licence, active_count)}


@router.get("/current")
def current(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    licence = current_licence_for_user(db, user)
    if not licence:
        return {"licence": None}
    ensure_current(licence)
    subscription_access = organisation_subscription_access(db, user.organisation_id)
    if not subscription_access.allowed:
        return {"licence": None, "subscription_access": subscription_access.payload()}
    active_count = db.scalar(select(func.count(DeviceActivation.id)).where(
        DeviceActivation.licence_id == licence.id,
        DeviceActivation.active.is_(True),
    )) or 0
    return {"licence": serialise(licence, active_count)}


@router.post("/validate")
def validate(
    payload: ValidateLicenceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    licence = current_licence_for_user(db, user)
    if not licence:
        raise HTTPException(status_code=404, detail="No active licence")
    ensure_current(licence)
    subscription_access = organisation_subscription_access(db, user.organisation_id)
    if not subscription_access.allowed:
        raise HTTPException(status_code=403, detail=subscription_access.message)
    activation = db.scalar(select(DeviceActivation).where(
        DeviceActivation.licence_id == licence.id,
        DeviceActivation.device_id == payload.device_id,
        DeviceActivation.active.is_(True),
    ))
    if not activation:
        raise HTTPException(status_code=403, detail="This device is not activated")
    activation.last_validated_at = datetime.now(timezone.utc)
    db.commit()
    active_count = db.scalar(select(func.count(DeviceActivation.id)).where(
        DeviceActivation.licence_id == licence.id,
        DeviceActivation.active.is_(True),
    )) or 0
    return {"valid": True, "licence": serialise(licence, active_count)}


@router.get("/entitlements")
def entitlements(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Return the authoritative product, sport and feature policy for this user."""
    licence = current_licence_for_user(db, user)
    if not licence:
        return {"licensed": False, "products": [], "sports": [], "features": [], "licence": None}
    if not licence_is_current(licence.status, licence.expires_at):
        return {"licensed": False, "products": [], "sports": [], "features": [], "licence": None}
    subscription_access = organisation_subscription_access(db, user.organisation_id)
    if not subscription_access.allowed:
        return {"licensed": False, "products": [], "sports": [], "features": [], "licence": None, "subscription_access": subscription_access.payload()}
    active_count = db.scalar(select(func.count(DeviceActivation.id)).where(
        DeviceActivation.licence_id == licence.id, DeviceActivation.active.is_(True)
    )) or 0
    payload = serialise(licence, active_count)
    platform_admin = bool(user.is_admin and user.organisation_id is None)
    access_role = access_role_for_licence(db, user, licence)
    payload["access_role"] = access_role
    payload["products"] = filter_products(
        licence.products_json, role=access_role, is_platform_admin=platform_admin, assigned_products=user.products_json
    )
    payload["sports"] = filter_sports(licence.sports_json, assigned_sports=user.sports_json)
    return {
        "licensed": True,
        "products": payload["products"],
        "sports": payload["sports"],
        "features": payload["features"],
        "licence": payload,
        "subscription_access": subscription_access.payload(),
    }


@router.post("/deactivate-device")
def deactivate_device(
    payload: DeactivateDeviceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    licence = db.scalar(select(Licence).where(Licence.user_id == user.id))
    if not licence:
        raise HTTPException(status_code=404, detail="No licence assigned")
    activation = db.scalar(select(DeviceActivation).where(
        DeviceActivation.licence_id == licence.id,
        DeviceActivation.device_id == payload.device_id,
        DeviceActivation.active.is_(True),
    ))
    if not activation:
        raise HTTPException(status_code=404, detail="Active device was not found")
    activation.active = False
    db.commit()
    return {"message": "Device deactivated"}
