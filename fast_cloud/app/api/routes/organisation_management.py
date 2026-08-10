from __future__ import annotations

import json
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import hash_password
from app.core.email import EmailDeliveryError, branded_action_email, send_email
from app.core.config import get_settings
from app.core.rate_limit import RateLimit, client_address, limiter
from app.db.session import get_db
from app.models import AuditLog, Club, DeviceActivation, DeviceAuditLog, Licence, Organisation, User
from app.api.routes.subscriptions import subscription_payload

router = APIRouter(prefix="/organisation-management", tags=["organisation-management"])
settings = get_settings()


class CreateUserRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=320)
    temporary_password: str = Field(default="", max_length=200)
    role: str = "analyst"
    products: list[str] = Field(default_factory=list)
    sports: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    full_name: str = Field(default="", max_length=160)
    role: str = "analyst"
    status: str = "active"
    products: list[str] = Field(default_factory=list)
    sports: list[str] = Field(default_factory=list)


class BrandingRequest(BaseModel):
    short_name: str = Field(default="", max_length=40)
    logo_url: str = Field(default="", max_length=500)
    primary_colour: str = Field(default="#19D978", max_length=16)
    secondary_colour: str = Field(default="#151A1D", max_length=16)
    accent_colour: str = Field(default="#19D978", max_length=16)


class ResetPasswordRequest(BaseModel):
    temporary_password: str = Field(min_length=10, max_length=200)


def _require_org_admin(user: User) -> int:
    if user.organisation_id is None or (user.role or "").lower() != "administrator":
        raise HTTPException(status_code=403, detail="Organisation administrator access required")
    return int(user.organisation_id)


def _loads(value: str | None, fallback):
    try:
        result = json.loads(value or "")
        return result if isinstance(result, type(fallback)) else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _hash_one_time_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_expired(value: datetime | None) -> bool:
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)


def _issue_invitation(db: Session, actor: User, target: User, organisation: Organisation, *, action: str) -> dict:
    token = secrets.token_urlsafe(40)
    target.invitation_token_hash = _hash_one_time_token(token)
    target.invitation_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.invite_expiry_hours)
    target.invited_at = datetime.now(timezone.utc)
    target.status = "invited"
    target.must_change_password = False
    invite_link = f"{settings.public_app_url.rstrip('/')}/accept-invite?token={token}"
    text_body, html_body = branded_action_email(
        heading=f"Join {organisation.name} on FAST",
        intro=f"You've been invited to join {organisation.name} on FAST Sports Analytics.",
        action_label="Accept invitation",
        action_url=invite_link,
        expiry_text=f"This secure invitation expires in {settings.invite_expiry_hours} hours and can only be used once.",
        footer_text="If you were not expecting this invitation, you can ignore this email.",
    )
    try:
        delivery = send_email(
            to_email=target.email,
            subject=f"You've been invited to {organisation.name} on FAST Sports Analytics",
            text=text_body,
            html=html_body,
        )
    except EmailDeliveryError as exc:
        target.invitation_token_hash = None
        target.invitation_expires_at = None
        _audit(
            db, actor, "invitation_delivery_failed", "organisation_user",
            target.id, target.email, str(exc)[:500],
        )
        raise HTTPException(status_code=502, detail="FAST could not deliver the invitation email. Check transactional email configuration and try again.") from exc
    _audit(
        db,
        actor,
        action,
        "organisation_user",
        target.id,
        target.email,
        f"Invitation issued; expires in {settings.invite_expiry_hours} hours; delivery={delivery.provider}.",
    )
    return {
        "delivery": delivery.provider if delivery.delivered else "development_console",
        "expires_at": target.invitation_expires_at.isoformat(),
        "development_invitation_token": token if settings.environment.lower() != "production" and not delivery.delivered else None,
    }


def _normalise_colour(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) in {4, 7} and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text.upper()
        except ValueError:
            pass
    return fallback

def _audit(db: Session, actor: User, action: str, target_type: str, target_id: int | None, label: str, details: str) -> None:
    db.add(AuditLog(
        admin_user_id=actor.id,
        action=action,
        category="organisation_management",
        target_type=target_type,
        target_id=target_id,
        target_label=label,
        details=details,
    ))


def _entitlements(organisation: Organisation) -> tuple[list[str], list[str]]:
    products: set[str] = set()
    sports: set[str] = set()
    for club in organisation.clubs:
        for licence in club.licences:
            if licence.status != "active":
                continue
            products.update(str(v) for v in _loads(licence.products_json, []) if str(v).strip())
            sports.update(str(v) for v in _loads(licence.sports_json, []) if str(v).strip())
    return sorted(products), sorted(sports)


def _role_allowed_products(role: str, organisation_products: list[str]) -> list[str]:
    role_key = str(role or "").strip().lower()
    licensed = {str(value).strip().lower() for value in organisation_products if str(value).strip()}
    if role_key == "administrator":
        allowed = licensed
    else:
        policy = {
            "analyst": {"analysis", "viewer"},
            "coach": {"viewer"},
            "scout": {"scout"},
        }
        allowed = licensed.intersection(policy.get(role_key, set()))
    return sorted(allowed)


def _overview(db: Session, organisation_id: int) -> dict:
    organisation = db.get(Organisation, organisation_id)
    if not organisation:
        raise HTTPException(status_code=404, detail="Organisation not found")
    products, sports = _entitlements(organisation)
    all_users = db.scalars(select(User).where(User.organisation_id == organisation_id).order_by(User.full_name, User.email)).all()
    users = [item for item in all_users if str(item.status or "").lower() != "removed"]
    devices = db.scalars(
        select(DeviceActivation)
        .join(Licence)
        .join(Club)
        .where(Club.organisation_id == organisation_id)
        .order_by(DeviceActivation.last_validated_at.desc())
    ).all()
    audits = db.scalars(
        select(AuditLog)
        .where(AuditLog.admin_user_id.in_([u.id for u in all_users] or [-1]))
        .order_by(AuditLog.created_at.desc())
        .limit(250)
    ).all()
    routine_actions = {
        "heartbeat", "device_heartbeat", "update_check", "product_inventory",
        "launcher_started", "device_telemetry", "session_refreshed",
    }
    meaningful_audits = [
        item for item in audits
        if str(item.action or "").lower() not in routine_actions
        and "heartbeat" not in str(item.action or "").lower()
    ][:100]
    active_users = sum(1 for item in users if item.status == "active")
    allocated_users = sum(1 for item in users if item.status in {"active", "invited"})
    active_devices = sum(1 for item in devices if item.active)
    subscription = subscription_payload(db, organisation_id)
    plan = subscription.get("plan") or {}
    max_devices = int(plan.get("max_devices") or 0)
    seat_limit = int(subscription.get("seat_override") or plan.get("included_seats") or organisation.max_seats or 0)
    subscription_status = str(subscription.get("status") or "unconfigured").lower()
    health_checks = [
        {"key": "subscription", "ok": subscription_status in {"active", "trial"}, "label": "Subscription", "detail": subscription.get("display_status") or "Plan not configured"},
        {"key": "seats", "ok": not seat_limit or allocated_users < seat_limit, "label": "User seats", "detail": f"{allocated_users} of {seat_limit} allocated" if seat_limit else f"{allocated_users} allocated"},
        {"key": "devices", "ok": not max_devices or active_devices < max_devices, "label": "Device allocation", "detail": f"{active_devices} of {max_devices} active" if max_devices else f"{active_devices} active"},
        {"key": "licence", "ok": bool(products or sports), "label": "Licence entitlements", "detail": f"{len(products)} products and {len(sports)} sports enabled"},
        {"key": "sync", "ok": any(item.last_validated_at for item in devices), "label": "Cloud sync", "detail": "Device telemetry received" if any(item.last_validated_at for item in devices) else "No device telemetry received"},
    ]
    return {
        "organisation": {
            "id": organisation.id,
            "name": organisation.name,
            "tier": organisation.subscription_tier,
            "status": organisation.status,
            "max_seats": organisation.max_seats,
            "seats_used": allocated_users,
            "active_users": active_users,
            "active_devices": active_devices,
            "expires_at": organisation.expires_at.isoformat() if organisation.expires_at else None,
            "products": products,
            "sports": sports,
            "subscription": subscription,
            "max_devices": max_devices or None,
            "health_checks": health_checks,
            "branding": {
                "short_name": organisation.short_name or organisation.name[:12],
                "logo_url": organisation.logo_url or "",
                "primary_colour": organisation.primary_colour or "#19D978",
                "secondary_colour": organisation.secondary_colour or "#151A1D",
                "accent_colour": organisation.accent_colour or "#19D978",
            },
        },
        "users": [{
            "id": item.id,
            "full_name": item.full_name or "",
            "email": item.email,
            "role": item.role or "analyst",
            "status": item.status,
            "products": _loads(item.products_json, []),
            "sports": _loads(item.sports_json, []),
            "must_change_password": bool(item.must_change_password),
            "last_login_at": item.last_login_at.isoformat() if item.last_login_at else None,
            "invited_at": item.invited_at.isoformat() if item.invited_at else None,
            "invitation_expires_at": item.invitation_expires_at.isoformat() if item.invitation_expires_at else None,
            "invitation_status": (
                "accepted" if item.status == "active" and item.invited_at
                else "expired" if item.status == "invited" and _is_expired(item.invitation_expires_at)
                else "pending" if item.status == "invited"
                else "not_applicable"
            ),
        } for item in users],
        "devices": [{
            "id": item.id,
            "device_id": item.device_id,
            "device_name": item.device_name or item.device_id,
            "active": bool(item.active),
            "version": item.installed_version,
            "last_seen_at": item.last_validated_at.isoformat() if item.last_validated_at else None,
            "deployment_ring": item.deployment_ring or organisation.deployment_ring,
        } for item in devices],
        "audit": [{
            "id": item.id,
            "created_at": item.created_at.isoformat(),
            "action": item.action,
            "target": item.target_label or "",
            "details": item.details or "",
        } for item in meaningful_audits],
    }


@router.get("")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    return _overview(db, organisation_id)


@router.post("/users")
def create_user(payload: CreateUserRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    organisation = db.get(Organisation, organisation_id)
    assert organisation is not None
    role = payload.role.lower().strip()
    if role not in {"administrator", "analyst", "coach", "scout"}:
        raise HTTPException(status_code=422, detail="Invalid role")
    email = payload.email.lower().strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    existing_user = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing_user and not (
        existing_user.organisation_id == organisation_id
        and str(existing_user.status or "").lower() == "removed"
    ):
        raise HTTPException(status_code=409, detail="That email already has an account")
    used = db.scalar(select(func.count(User.id)).where(User.organisation_id == organisation_id, User.status.in_(["active", "invited"]))) or 0
    if used >= organisation.max_seats:
        raise HTTPException(status_code=409, detail="All organisation seats are currently allocated")
    allowed_products, allowed_sports = _entitlements(organisation)
    temporary_password = payload.temporary_password.strip()
    if temporary_password and len(temporary_password) < 10:
        raise HTTPException(status_code=422, detail="Temporary passwords must contain at least 10 characters")
    if existing_user:
        new_user = existing_user
        new_user.full_name = payload.full_name.strip()
        new_user.password_hash = hash_password(temporary_password or secrets.token_urlsafe(48))
        new_user.email_verified = bool(temporary_password)
        new_user.status = "active" if temporary_password else "invited"
        new_user.role = role
        new_user.is_admin = False
        new_user.organisation_id = organisation_id
        new_user.products_json = json.dumps([
            v for v in payload.products if v in _role_allowed_products(role, allowed_products)
        ])
        new_user.sports_json = json.dumps([v for v in payload.sports if v in allowed_sports])
        new_user.must_change_password = bool(temporary_password)
        new_user.invited_at = datetime.now(timezone.utc)
        new_user.invitation_token_hash = None
        new_user.invitation_expires_at = None
        new_user.password_reset_token_hash = None
        new_user.password_reset_expires_at = None
        db.add(new_user)
        _audit(db, user, "restored", "organisation_user", new_user.id, new_user.email, f"{role.title()} account restored to the organisation.")
    else:
        new_user = User(
            email=email,
            full_name=payload.full_name.strip(),
            password_hash=hash_password(temporary_password or secrets.token_urlsafe(48)),
            email_verified=bool(temporary_password),
            status="active" if temporary_password else "invited",
            role=role,
            is_admin=False,
            organisation_id=organisation_id,
            products_json=json.dumps([
                v for v in payload.products if v in _role_allowed_products(role, allowed_products)
            ]),
            sports_json=json.dumps([v for v in payload.sports if v in allowed_sports]),
            must_change_password=bool(temporary_password),
            invited_at=datetime.now(timezone.utc),
        )
        db.add(new_user)
        db.flush()
    invitation = None
    if temporary_password:
        _audit(db, user, "created", "organisation_user", new_user.id, new_user.email, f"{role.title()} account created with a temporary password.")
    else:
        invitation = _issue_invitation(db, user, new_user, organisation, action="invitation_sent")
    db.commit()
    result = _overview(db, organisation_id)
    if invitation:
        result["invitation"] = invitation
    return result


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UpdateUserRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    target = db.get(User, user_id)
    if not target or target.organisation_id != organisation_id:
        raise HTTPException(status_code=404, detail="Organisation user not found")
    role = payload.role.lower().strip()
    if role not in {"administrator", "analyst", "coach", "scout"}:
        raise HTTPException(status_code=422, detail="Invalid role")
    status = payload.status.lower().strip()
    if status not in {"active", "suspended", "invited"}:
        raise HTTPException(status_code=422, detail="Invalid status")
    if target.id == user.id and (role != "administrator" or status != "active"):
        raise HTTPException(status_code=409, detail="You cannot remove your own organisation administrator access")
    organisation = db.get(Organisation, organisation_id)
    assert organisation is not None
    allowed_products, allowed_sports = _entitlements(organisation)
    target.full_name = payload.full_name.strip() or None
    target.role = role
    target.is_admin = False
    target.status = status
    role_products = _role_allowed_products(role, allowed_products)
    assigned_products = [v for v in payload.products if v in role_products]
    assigned_sports = [v for v in payload.sports if v in allowed_sports]
    target.products_json = json.dumps(assigned_products)
    target.sports_json = json.dumps(assigned_sports)
    _audit(
        db,
        user,
        "updated",
        "organisation_user",
        target.id,
        target.email,
        f"Role {role}; status {status}; products {', '.join(assigned_products) or 'none'}; sports {', '.join(assigned_sports) or 'none'}.",
    )
    db.commit()
    return _overview(db, organisation_id)


@router.delete("/users/{user_id}")
def remove_user(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    target = db.get(User, user_id)
    if not target or target.organisation_id != organisation_id or str(target.status or "").lower() == "removed":
        raise HTTPException(status_code=404, detail="Organisation user not found")
    if target.id == user.id:
        raise HTTPException(status_code=409, detail="You cannot remove your own organisation administrator account")
    target.status = "removed"
    target.products_json = "[]"
    target.sports_json = "[]"
    target.must_change_password = False
    target.invitation_token_hash = None
    target.invitation_expires_at = None
    target.password_reset_token_hash = None
    target.password_reset_expires_at = None
    _audit(
        db,
        user,
        "removed",
        "organisation_user",
        target.id,
        target.email,
        "User removed from organisation access and seat allocation reclaimed.",
    )
    db.commit()
    return _overview(db, organisation_id)


@router.post("/users/{user_id}/resend-invite")
def resend_user_invitation(
    user_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    limiter.enforce(
        f"invite-resend:{client_address(request)}:{user_id}",
        RateLimit(settings.invitation_resend_rate_attempts, settings.invitation_resend_rate_window_seconds),
    )
    organisation_id = _require_org_admin(user)
    organisation = db.get(Organisation, organisation_id)
    target = db.get(User, user_id)
    if not organisation or not target or target.organisation_id != organisation_id:
        raise HTTPException(status_code=404, detail="Organisation user not found")
    if target.status in {"suspended", "removed"}:
        raise HTTPException(status_code=409, detail="Suspended or removed users cannot receive invitations")
    if target.id == user.id:
        raise HTTPException(status_code=409, detail="You cannot invite your own administrator account")
    invitation = _issue_invitation(db, user, target, organisation, action="invitation_resent")
    db.commit()
    result = _overview(db, organisation_id)
    result["invitation"] = invitation
    return result


@router.post("/devices/{device_id}/deactivate")
def deactivate_device(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    device = db.scalar(
        select(DeviceActivation).join(Licence).join(Club).where(
            DeviceActivation.id == device_id,
            Club.organisation_id == organisation_id,
        )
    )
    if not device:
        raise HTTPException(status_code=404, detail="Organisation device not found")
    device.active = False
    db.add(DeviceAuditLog(device_activation_id=device.id, admin_user_id=user.id, action="deactivated", details="Device deactivated from Launcher organisation management."))
    _audit(db, user, "device_deactivated", "organisation_device", device.id, device.device_name or device.device_id, "Device seat reclaimed from Launcher.")
    db.commit()
    return _overview(db, organisation_id)


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, payload: ResetPasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    target = db.get(User, user_id)
    if not target or target.organisation_id != organisation_id:
        raise HTTPException(status_code=404, detail="Organisation user not found")
    if target.id == user.id:
        raise HTTPException(status_code=409, detail="Use Change Password to update your own administrator password")
    if str(target.status or "").lower() == "removed":
        raise HTTPException(status_code=409, detail="Removed users must be invited back to the organisation before a password can be issued")
    target.password_hash = hash_password(payload.temporary_password)
    target.must_change_password = True
    if target.status == "invited":
        target.status = "active"
    target.invited_at = datetime.now(timezone.utc)
    _audit(db, user, "password_reset", "organisation_user", target.id, target.email, "Temporary password issued; password change required at next sign-in.")
    db.commit()
    return _overview(db, organisation_id)


@router.post("/devices/{device_id}/reactivate")
def reactivate_device(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    device = db.scalar(
        select(DeviceActivation).join(Licence).join(Club).where(
            DeviceActivation.id == device_id,
            Club.organisation_id == organisation_id,
        )
    )
    if not device:
        raise HTTPException(status_code=404, detail="Organisation device not found")
    organisation = db.get(Organisation, organisation_id)
    subscription = subscription_payload(db, organisation_id)
    plan = subscription.get("plan") or {}
    max_devices = int(plan.get("max_devices") or 0)
    active_devices = db.scalar(
        select(func.count(DeviceActivation.id))
        .join(Licence).join(Club)
        .where(Club.organisation_id == organisation_id, DeviceActivation.active.is_(True))
    ) or 0
    if max_devices and not device.active and active_devices >= max_devices:
        raise HTTPException(status_code=409, detail="All organisation device allocations are currently in use")
    device.active = True
    db.add(DeviceAuditLog(device_activation_id=device.id, admin_user_id=user.id, action="reactivated", details="Device reactivated from Launcher organisation management."))
    _audit(db, user, "device_reactivated", "organisation_device", device.id, device.device_name or device.device_id, "Device access restored from Launcher.")
    db.commit()
    return _overview(db, organisation_id)


@router.patch("/branding")
def update_branding(payload: BrandingRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    organisation = db.get(Organisation, organisation_id)
    if not organisation:
        raise HTTPException(status_code=404, detail="Organisation not found")
    organisation.short_name = payload.short_name.strip() or None
    organisation.logo_url = payload.logo_url.strip() or None
    organisation.primary_colour = _normalise_colour(payload.primary_colour, "#19D978")
    organisation.secondary_colour = _normalise_colour(payload.secondary_colour, "#151A1D")
    organisation.accent_colour = _normalise_colour(payload.accent_colour, organisation.primary_colour)
    _audit(db, user, "branding_updated", "organisation", organisation.id, organisation.name, "Organisation name abbreviation, crest reference and colours updated.")
    db.commit()
    return _overview(db, organisation_id)
