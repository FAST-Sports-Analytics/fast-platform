from datetime import datetime, timedelta, timezone
import json
import secrets
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jwt import InvalidTokenError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.email import EmailDeliveryError, branded_action_email, send_email
from app.core.config import get_settings
from app.core.rate_limit import RateLimit, client_address, limiter
from app.core.entitlements import filter_products, filter_sports, licence_is_current
from app.core.subscription_access import organisation_subscription_access
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.api.deps import get_current_user
from app.api.routes.subscriptions import subscription_payload
from app.db.session import get_db
from app.models import AuditLog, Club, ClubMember, DeviceActivation, DeviceAuditLog, Licence, User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SessionStatusRequest,
    TokenResponse,
    VerifyEmailRequest,
    ChangePasswordRequest,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
    AcceptInvitationRequest,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def _hash_one_time_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_expired(value: datetime | None) -> bool:
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < datetime.now(timezone.utc)



def user_payload(user: User) -> dict:
    platform_admin = bool(user.is_admin and user.organisation_id is None)
    organisation_admin = bool(
        user.organisation_id is not None
        and (user.role or "").lower() == "administrator"
    )
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "email_verified": user.email_verified,
        "status": user.status,
        # ``is_admin`` is retained for backwards compatibility, but now means
        # platform-wide FAST administration only. Organisation administrators
        # are deliberately scoped through ``organisation_admin``.
        "is_admin": platform_admin,
        "platform_admin": platform_admin,
        "role": "platform_administrator" if platform_admin else (user.role or "analyst"),
        "organisation": {"id": user.organisation.id, "name": user.organisation.name} if user.organisation else None,
        "assigned_products": json.loads(user.products_json or "[]"),
        "assigned_sports": json.loads(user.sports_json or "[]"),
        "must_change_password": bool(user.must_change_password),
        "organisation_admin": organisation_admin,
        "admin_scope": "platform" if platform_admin else ("organisation" if organisation_admin else "none"),
    }


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
        "short_name": getattr(organisation, "short_name", None) or organisation.name[:12],
        "primary_colour": getattr(organisation, "primary_colour", None) or "#19D978",
        "secondary_colour": getattr(organisation, "secondary_colour", None) or "#151A1D",
        "accent_colour": getattr(organisation, "accent_colour", None) or "#19D978",
        "status": organisation.status,
        "club": {"id": club.id, "name": club.name} if club else None,
    }


def _current_licence(db: Session, user: User) -> Licence | None:
    """Resolve individual, club-member, or organisation-managed licences."""
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



def _access_role_for_licence(db: Session, user: User, licence: Licence) -> str:
    """Resolve the role that governs access to the selected licence.

    A club membership role is authoritative when it is a product-bearing role.
    Owner/member are relationship labels, so they fall back to the organisation
    user's role. Platform administrators retain administrator access.
    """
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

def licence_payload(db: Session, user: User) -> dict | None:
    licence = _current_licence(db, user)
    if not licence:
        return None
    active_devices = db.scalar(select(func.count(DeviceActivation.id)).where(
        DeviceActivation.licence_id == licence.id,
        DeviceActivation.active.is_(True),
    )) or 0
    if not licence_is_current(licence.status, licence.expires_at):
        return None
    subscription_access = organisation_subscription_access(db, user.organisation_id)
    if not subscription_access.allowed:
        return None
    platform_admin = bool(user.is_admin and user.organisation_id is None)
    access_role = _access_role_for_licence(db, user, licence)
    products = filter_products(
        licence.products_json,
        role=access_role,
        is_platform_admin=platform_admin,
        assigned_products=user.products_json,
    )
    sports = filter_sports(licence.sports_json, assigned_sports=user.sports_json)
    return {
        "id": licence.id,
        "tier": licence.tier,
        "products": products,
        "sports": sports,
        "features": json.loads(getattr(licence, "features_json", "[]") or "[]"),
        "expires_at": licence.expires_at,
        "max_devices": licence.max_devices,
        "active_devices": active_devices,
        "status": licence.status,
        "code_last_four": licence.code_last_four,
        "owner_type": licence.owner_type,
        "owner_user_id": licence.user_id,
        "owner_club_id": licence.club_id,
        "max_users": licence.max_users,
        "access_role": access_role,
        "organisation": organisation_payload(licence),
        "subscription": subscription_payload(db, user.organisation_id) if user.organisation_id else None,
        "subscription_access": subscription_access.payload(),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    token = secrets.token_urlsafe(32)
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        verification_token=token,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    response = {
        "message": "Account created. Verify the email before production access is enabled.",
        "user": user_payload(user),
    }
    if settings.environment.lower() != "production":
        response["development_verification_token"] = token
    return response


@router.post("/verify-email")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.verification_token == payload.token))
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    user.email_verified = True
    user.verification_token = None
    db.commit()
    return {"message": "Email verified"}


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is suspended")
    user.last_login_at = datetime.now(timezone.utc)
    db.add(AuditLog(admin_user_id=user.id, action="login", category="user_activity", target_type="user", target_id=user.id, target_label=user.email, details=f"Launcher login as {('platform administrator' if (user.is_admin and user.organisation_id is None) else user.role or 'analyst')}"))
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_payload(user),
        licence=licence_payload(db, user),
    )


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.add(AuditLog(admin_user_id=user.id, action="password_changed", category="user_activity", target_type="user", target_id=user.id, target_label=user.email, details="User changed their password."))
    db.commit()
    return {"message": "Password changed"}


@router.post("/request-password-reset")
def request_password_reset(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    email = payload.email.lower().strip()
    limiter.enforce(
        f"password-reset:{client_address(request)}:{email}",
        RateLimit(settings.password_reset_rate_attempts, settings.password_reset_rate_window_seconds),
    )
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    response = {"message": "If that account exists, password recovery instructions have been sent."}
    if not user or user.status not in {"active", "invited"}:
        return response

    token = secrets.token_urlsafe(40)
    user.password_reset_token_hash = _hash_one_time_token(token)
    user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_expiry_minutes)
    db.add(AuditLog(
        admin_user_id=user.id,
        action="password_reset_requested",
        category="account_recovery",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details=f"Password recovery requested; token expires in {settings.password_reset_expiry_minutes} minutes.",
    ))
    db.commit()
    reset_link = f"{settings.public_app_url.rstrip('/')}/reset-password?token={token}"
    text_body, html_body = branded_action_email(
        heading="Reset your FAST password",
        intro="A password reset was requested for your FAST Sports Analytics account.",
        action_label="Reset password",
        action_url=reset_link,
        expiry_text=f"This secure link expires in {settings.password_reset_expiry_minutes} minutes and can only be used once.",
        footer_text="If you did not request this password reset, you can safely ignore this email.",
    )
    try:
        delivery = send_email(
            to_email=user.email,
            subject="Reset your FAST Sports Analytics password",
            text=text_body,
            html=html_body,
        )
    except EmailDeliveryError as exc:
        # Keep the public response deliberately generic so recovery requests do
        # not reveal whether an address exists. Invalidate the undispatched
        # token instead of leaving a usable recovery credential behind.
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        db.add(AuditLog(
            admin_user_id=user.id,
            action="password_reset_delivery_failed",
            category="account_recovery",
            target_type="user",
            target_id=user.id,
            target_label=user.email,
            details=str(exc)[:500],
        ))
        db.commit()
        return response
    response["delivery"] = delivery.provider if delivery.delivered else "development_console"
    # Never return a recovery token when the message was actually delivered.
    # Development tokens are reserved for the explicit console fallback only.
    if settings.environment.lower() != "production" and not delivery.delivered:
        response["development_reset_token"] = token
    return response


@router.post("/reset-password")
def reset_password(payload: PasswordResetConfirmRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    limiter.enforce(
        f"reset-submit:{client_address(request)}",
        RateLimit(settings.token_submit_rate_attempts, settings.token_submit_rate_window_seconds),
    )
    token_hash = _hash_one_time_token(payload.token.strip())
    user = db.scalar(select(User).where(User.password_reset_token_hash == token_hash))
    if not user or _is_expired(user.password_reset_expires_at):
        raise HTTPException(status_code=400, detail="This password reset token is invalid or has expired")
    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="This account is suspended")
    user.password_hash = hash_password(payload.new_password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    user.must_change_password = False
    if user.status == "invited":
        user.status = "active"
    db.add(AuditLog(
        admin_user_id=user.id,
        action="password_reset_completed",
        category="account_recovery",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details="Password reset completed using a one-time recovery token.",
    ))
    db.commit()
    return {"message": "Password reset complete. You can now sign in."}


@router.post("/accept-invitation")
def accept_invitation(payload: AcceptInvitationRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    limiter.enforce(
        f"invite-accept:{client_address(request)}",
        RateLimit(settings.token_submit_rate_attempts, settings.token_submit_rate_window_seconds),
    )
    token_hash = _hash_one_time_token(payload.token.strip())
    user = db.scalar(select(User).where(User.invitation_token_hash == token_hash))
    if not user or _is_expired(user.invitation_expires_at):
        raise HTTPException(status_code=400, detail="This invitation is invalid or has expired")
    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="This invitation is no longer available")
    user.password_hash = hash_password(payload.new_password)
    user.status = "active"
    user.email_verified = True
    user.must_change_password = False
    user.invitation_token_hash = None
    user.invitation_expires_at = None
    db.add(AuditLog(
        admin_user_id=user.id,
        action="invitation_accepted",
        category="account_onboarding",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details="Organisation invitation accepted and account activated.",
    ))
    db.commit()
    return {"message": "Invitation accepted. You can now sign in."}


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user_id = decode_token(payload.refresh_token, expected_type="refresh")
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc
    user = db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="Account unavailable")
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_payload(user),
        licence=licence_payload(db, user),
    )


@router.post("/session")
def session_status(
    payload: SessionStatusRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authoritative account, licence and device entitlement state.

    The Launcher uses this endpoint after login and session restoration so product
    access is never granted from stale locally cached licence data.
    """
    subscription_access = organisation_subscription_access(db, user.organisation_id)
    licence_data = licence_payload(db, user)
    device_activated = False
    device_message = subscription_access.message if not subscription_access.allowed else "No active licence is assigned to this account."

    if licence_data:
        # Look up the device regardless of active state.  An inactive row means an
        # administrator deliberately reclaimed this allocation, so session refresh
        # must never silently reactivate it.
        activation = db.scalar(select(DeviceActivation).where(
            DeviceActivation.licence_id == licence_data["id"],
            DeviceActivation.device_id == payload.device_id,
        ))
        if activation and activation.active:
            activation.device_name = payload.device_name or activation.device_name
            activation.last_validated_at = datetime.now(timezone.utc)
            db.commit()
            device_activated = True
            device_message = "This device is activated."
        elif activation and not activation.active:
            device_message = "This device has been deactivated. Ask your administrator to reactivate it before using FAST applications."
        elif user.organisation_id is not None and licence_data.get("owner_type") == "club":
            active_count = db.scalar(select(func.count(DeviceActivation.id)).where(
                DeviceActivation.licence_id == licence_data["id"],
                DeviceActivation.active.is_(True),
            )) or 0
            if active_count < int(licence_data.get("max_devices") or 1):
                activation = DeviceActivation(
                    licence_id=licence_data["id"],
                    device_id=payload.device_id,
                    device_name=payload.device_name,
                    active=True,
                    last_validated_at=datetime.now(timezone.utc),
                )
                db.add(activation)
                db.flush()
                db.add(DeviceAuditLog(
                    device_activation_id=activation.id,
                    admin_user_id=user.id,
                    action="activated",
                    details=f"{payload.device_name or payload.device_id} activated automatically from FAST Launcher.",
                ))
                db.commit()
                licence_data["active_devices"] = active_count + 1
                device_activated = True
                device_message = "This organisation device has been activated."
            else:
                db.add(DeviceAuditLog(
                    device_activation_id=None,
                    admin_user_id=user.id,
                    action="seat_limit_blocked",
                    details=f"Activation blocked for {payload.device_name or payload.device_id}; licence device limit reached.",
                ))
                db.commit()
                device_message = "The organisation licence has reached its device limit."
        else:
            device_message = "This licence is not activated on this device."

    return {
        "user": user_payload(user),
        "licence": licence_data,
        "device_activated": device_activated,
        "device_message": device_message,
        "subscription_access": subscription_access.payload(),
    }
