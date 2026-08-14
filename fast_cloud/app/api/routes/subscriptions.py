from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.email import EmailDeliveryError, branded_action_email, send_email
from app.core.rate_limit import RateLimit, client_address, limiter
from app.core.security import generate_licence_code, hash_licence_code, hash_password, normalise_licence_code
from app.db.session import SessionLocal, get_db
from app.models import AuditLog, BillingWebhookEvent, Club, ClubMember, Licence, Organisation, OrganisationSubscription, Sport, SubscriptionPlan, User

try:
    import stripe
except ImportError:  # Billing remains safely unavailable until dependency is installed.
    stripe = None

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
settings = get_settings()

# Canonical public sport entitlement catalogue. Keep these keys aligned with
# FAST Analysis src/core/sports/sport_type.py.
SUPPORTED_SPORTS = [
    ("football", "Football"),
    ("futsal", "Futsal"),
    ("rugby_union", "Rugby Union"),
    ("rugby_league", "Rugby League"),
    ("basketball", "Basketball"),
    ("field_hockey", "Field Hockey"),
    ("ice_hockey", "Ice Hockey"),
    ("cricket", "Cricket"),
    ("netball", "Netball"),
    ("volleyball", "Volleyball"),
    ("handball", "Handball"),
    ("american_football", "American Football"),
    ("tennis", "Tennis"),
    ("baseball", "Baseball"),
]
SUPPORTED_SPORT_KEYS = {key for key, _name in SUPPORTED_SPORTS}


def _loads(value: str | None, fallback):
    try:
        result = json.loads(value or "")
        return result if isinstance(result, type(fallback)) else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _obj_get(value, key: str, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)




def _hash_one_time_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalise_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if len(email) < 5 or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Enter a valid work email address")
    return email


def _normalise_sport(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")[:80]


def _send_checkout_invitation(db: Session, user: User, organisation: Organisation) -> None:
    token = secrets.token_urlsafe(40)
    user.invitation_token_hash = _hash_one_time_token(token)
    user.invitation_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.invite_expiry_hours)
    user.invited_at = datetime.now(timezone.utc)
    user.status = "invited"
    user.must_change_password = False
    db.commit()

    invite_link = f"{settings.public_app_url.rstrip('/')}/accept-invite?token={token}"
    text_body, html_body = branded_action_email(
        heading=f"Welcome to {organisation.name} on FAST",
        intro="Your FAST Sports Analytics subscription is ready. Activate your administrator account to continue.",
        action_label="Activate FAST account",
        action_url=invite_link,
        expiry_text=f"This secure invitation expires in {settings.invite_expiry_hours} hours and can only be used once.",
        footer_text="If you did not purchase this FAST subscription, contact support@fastsportsanalytics.com.",
    )
    try:
        send_email(
            to_email=user.email,
            subject=f"Activate your {organisation.name} FAST account",
            text=text_body,
            html=html_body,
        )
    except EmailDeliveryError:
        # Do not reject Stripe's webhook after payment. The platform owner can
        # resend the invitation from FAST Cloud if transactional email fails.
        return


def _provision_public_checkout(db: Session, session, subscription) -> None:
    session_metadata = _obj_get(session, "metadata", {}) or {}
    if str(_obj_get(session_metadata, "fast_public_checkout", "")) != "1":
        return

    subscription_id = str(_obj_get(subscription, "id", "") or "")
    if subscription_id:
        existing_subscription = db.scalar(
            select(OrganisationSubscription).where(OrganisationSubscription.external_subscription_id == subscription_id)
        )
        if existing_subscription:
            _sync_stripe_subscription(db, subscription)
            return

    plan_id = str(_obj_get(session_metadata, "fast_plan_id", "") or "")
    if not plan_id.isdigit():
        return
    plan = db.get(SubscriptionPlan, int(plan_id))
    if not plan:
        return

    email = _normalise_email(str(_obj_get(session_metadata, "fast_contact_email", "") or ""))
    organisation_name = str(_obj_get(session_metadata, "fast_organisation_name", "") or "").strip()[:180]
    contact_name = str(_obj_get(session_metadata, "fast_contact_name", "") or "").strip()[:160]
    sport = _normalise_sport(str(_obj_get(session_metadata, "fast_sport", "") or ""))
    interval = str(_obj_get(session_metadata, "fast_billing_interval", "monthly") or "monthly")
    if len(organisation_name) < 2 or not contact_name:
        return

    existing_user = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing_user:
        # Idempotent retry: if a previous delivery already created the account,
        # bind the Stripe subscription to that organisation and continue.
        if existing_user.organisation_id:
            organisation = db.get(Organisation, int(existing_user.organisation_id))
            if organisation:
                metadata = dict(_obj_get(subscription, "metadata", {}) or {})
                metadata.update({
                    "fast_organisation_id": str(organisation.id),
                    "fast_plan_id": str(plan.id),
                    "fast_billing_interval": interval,
                })
                stripe.Subscription.modify(subscription_id, metadata=metadata)
                refreshed = stripe.Subscription.retrieve(subscription_id)
                _sync_stripe_subscription(db, refreshed)
        return

    organisation = db.scalar(select(Organisation).where(func.lower(Organisation.name) == organisation_name.lower()))
    if organisation:
        return

    plan_sports = _loads(plan.sports_json, [])
    # Public Starter/Professional checkout sells a selected sport entitlement.
    # Respect the customer's choice even when a seeded plan carries football as
    # its display/default sport.
    selected_sports = ([sport] if sport else plan_sports)
    organisation = Organisation(
        name=organisation_name,
        contact_name=contact_name,
        contact_email=email,
        subscription_tier=plan.name,
        sports_json=json.dumps(selected_sports),
        max_seats=plan.included_seats,
        status="active",
    )
    db.add(organisation)
    db.flush()

    products = _loads(plan.products_json, [])
    admin_user = User(
        email=email,
        full_name=contact_name,
        password_hash=hash_password(secrets.token_urlsafe(48)),
        email_verified=False,
        status="invited",
        is_admin=False,
        organisation_id=organisation.id,
        role="administrator",
        products_json=json.dumps(products),
        sports_json=json.dumps(selected_sports),
        must_change_password=False,
        invited_at=datetime.now(timezone.utc),
    )
    db.add(admin_user)
    db.flush()

    item = OrganisationSubscription(
        organisation_id=organisation.id,
        plan_id=plan.id,
        status="active",
        billing_interval=interval,
        billing_provider="stripe",
        external_customer_id=str(_obj_get(subscription, "customer", "") or "") or None,
        external_subscription_id=subscription_id or None,
    )
    db.add(item)
    db.flush()

    metadata = dict(_obj_get(subscription, "metadata", {}) or {})
    metadata.update({
        "fast_organisation_id": str(organisation.id),
        "fast_plan_id": str(plan.id),
        "fast_billing_interval": interval,
    })
    stripe.Subscription.modify(subscription_id, metadata=metadata)
    refreshed = stripe.Subscription.retrieve(subscription_id)
    _sync_stripe_subscription(db, refreshed)
    db.commit()
    _send_checkout_invitation(db, admin_user, organisation)


def _stripe_secret_key() -> str:
    # FAST Cloud normally reads FAST_CLOUD_STRIPE_SECRET_KEY because Settings
    # uses the FAST_CLOUD_ prefix.  Accept the shorter Railway variable too so
    # an existing deployment does not silently report billing as unavailable.
    return str(settings.stripe_secret_key or os.getenv("STRIPE_SECRET_KEY", "")).strip()


def _stripe_webhook_secret() -> str:
    return str(settings.stripe_webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET", "")).strip()


def _stripe_ready(*, webhook: bool = False) -> bool:
    if stripe is None or not _stripe_secret_key():
        return False
    return bool(_stripe_webhook_secret()) if webhook else True


def _configure_stripe() -> None:
    if stripe is not None:
        stripe.api_key = _stripe_secret_key()


# Stable FAST catalogue lookup keys.  The Professional sandbox prices currently
# resolve to price_1U3DxcGksGfK5ZjdPqDjvJb7 (monthly) and
# price_1U3DxcGksGfK5ZjdRvwhIQWd (annual).  Checkout resolves by lookup key so
# future Stripe price replacements do not require another code change.
_STRIPE_LOOKUP_KEYS: dict[tuple[str, str], str] = {
    ("starter", "monthly"): "fast_starter_monthly",
    ("starter", "annual"): "fast_starter_annual",
    ("professional", "monthly"): "fast_professional_monthly",
    ("professional", "annual"): "fast_professional_annual",
}

# Known Stripe catalogue IDs are kept as a fallback for dashboard-created
# prices where a lookup key was omitted.  The live subscription price is the
# source of truth for tier switches; checkout metadata is only a fallback.
_STRIPE_PRICE_PLAN_KEYS: dict[str, tuple[str, str]] = {
    "price_1U3KSfGksGfK5ZjdoBKFlQOG": ("starter", "monthly"),
    "price_1U3KT1GksGfK5ZjdErkEpH85": ("starter", "annual"),
    "price_1U3DxcGksGfK5ZjdPqDjvJb7": ("professional", "monthly"),
    "price_1U3DxcGksGfK5ZjdRvwhIQWd": ("professional", "annual"),
}


def _stripe_price_for_plan(plan: SubscriptionPlan, interval: str):
    plan_key = str(plan.name or "").strip().lower()
    lookup_key = _STRIPE_LOOKUP_KEYS.get((plan_key, interval))
    if not lookup_key:
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")

    _configure_stripe()
    price = None
    try:
        prices = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1)
        data = _obj_get(prices, "data", []) or []
        if data:
            price = data[0]
        else:
            # Dashboard-created sandbox prices do not necessarily have a lookup
            # key. Fall back to FAST's known catalogue IDs so public checkout is
            # still usable, while retaining the validation below as the safety
            # boundary. Live catalogue prices should continue to use lookup keys.
            known_price_id = next((
                price_id
                for price_id, mapped in _STRIPE_PRICE_PLAN_KEYS.items()
                if mapped == (plan_key, interval)
            ), None)
            if known_price_id:
                candidate = stripe.Price.retrieve(known_price_id)
                if bool(_obj_get(candidate, "active", True)):
                    price = candidate
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe price catalogue could not be read: {exc}") from exc

    if price is None:
        raise HTTPException(status_code=409, detail=f"Stripe price {lookup_key} is not configured yet")

    expected_amount = plan.monthly_price_pence if interval == "monthly" else plan.annual_price_pence
    actual_amount = int(_obj_get(price, "unit_amount", 0) or 0)
    actual_currency = str(_obj_get(price, "currency", "") or "").lower()
    recurring = _obj_get(price, "recurring", {}) or {}
    actual_interval = str(_obj_get(recurring, "interval", "") or "").lower()
    expected_interval = "month" if interval == "monthly" else "year"
    if actual_amount != expected_amount or actual_currency != settings.billing_currency.lower() or actual_interval != expected_interval:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Stripe price {lookup_key} does not match the FAST {plan.name} {interval} plan "
                f"({expected_amount / 100:.2f} {settings.billing_currency.upper()}/{expected_interval})."
            ),
        )
    return price


def _require_org_admin(user: User) -> int:
    if user.organisation_id is None:
        raise HTTPException(status_code=400, detail="This account is not attached to an organisation")
    if not user.is_admin and str(user.role or "").lower() != "administrator":
        raise HTTPException(status_code=403, detail="Organisation administrator access required")
    return int(user.organisation_id)


def plan_payload(plan: SubscriptionPlan | None) -> dict | None:
    if not plan:
        return None
    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description or "",
        "monthly_price_pence": plan.monthly_price_pence,
        "annual_price_pence": plan.annual_price_pence,
        "trial_days": plan.trial_days,
        "included_seats": plan.included_seats,
        "max_devices": plan.max_devices,
        "products": _loads(plan.products_json, []),
        "sports": _loads(plan.sports_json, []),
        "features": _loads(plan.features_json, {}),
        "cloud_storage_gb": plan.cloud_storage_gb,
        "self_service_upgrades": bool(plan.self_service_upgrades),
        "active": bool(plan.active),
    }


def subscription_payload(db: Session, organisation_id: int, *, refresh_provider: bool = False) -> dict:
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if (
        refresh_provider
        and item
        and item.billing_provider == "stripe"
        and item.external_subscription_id
        and _stripe_ready()
    ):
        # Organisation Management is an explicit customer/admin refresh. Re-read
        # Stripe here so the displayed cancellation/renewal state is authoritative
        # even if a Billing Portal webhook arrived out of order or was processed
        # before Stripe's retrieve endpoint reflected the final mutation. This is
        # intentionally opt-in so ordinary Launcher session/licence polling does
        # not make a Stripe API call on every request.
        try:
            _configure_stripe()
            remote = stripe.Subscription.retrieve(item.external_subscription_id)
            # We already know which FAST organisation owns this subscription.
            # Do not depend on Stripe metadata being present on every retrieved
            # object; older subscriptions or portal mutations may not carry it.
            _sync_stripe_subscription(
                db,
                remote,
                organisation_id_override=organisation_id,
            )
            # get_db() does not auto-commit on request completion. Persist the
            # provider reconciliation performed by this explicit refresh so the
            # next Launcher request sees the same cancellation state.
            db.commit()
            item = db.scalar(
                select(OrganisationSubscription).where(
                    OrganisationSubscription.organisation_id == organisation_id
                )
            )
        except Exception:
            # Keep Organisation Management available if Stripe is temporarily
            # unreachable; the last successfully synchronised FAST state remains
            # the fallback and the normal webhook path can repair it later.
            pass
    if not item:
        return {
            "status": "unconfigured",
            "display_status": "Plan not configured",
            "plan": None,
            "billing_interval": None,
            "period_label": "Not set",
            "billing_ready": False,
            "provider_available": _stripe_ready(),
            "can_manage_billing": False,
            "seat_limit": None,
            "seats_used": 0,
            "seat_over_limit": False,
            "seat_over_by": 0,
            "device_limit": None,
        }
    status = str(item.status or "unconfigured").lower()
    period_value = item.trial_ends_at if status == "trial" else item.current_period_ends_at
    period_label = "Trial ends" if status == "trial" else ("Access ends" if item.cancel_at_period_end else "Renews")
    display_status = (
        "Active — Cancelling"
        if status == "active" and item.cancel_at_period_end
        else str(item.status or "unconfigured").replace("_", " ").title()
    )
    billing_ready = bool(item.billing_provider == "stripe" and item.external_customer_id and _stripe_ready())

    # Stripe quantity scales plan capacity. ``seat_override`` stores the paid
    # user capacity after each Stripe sync; derive the matching device capacity
    # from the plan's base bundle so all API/UI checks use the same allowance.
    effective_plan = plan_payload(item.plan)
    seat_limit = None
    device_limit = None
    if item.plan:
        base_seats = max(1, int(item.plan.included_seats or 1))
        base_devices = max(1, int(item.plan.max_devices or 1))
        seat_limit = max(1, int(item.seat_override or base_seats))
        quantity = max(1, (seat_limit + base_seats - 1) // base_seats)
        device_limit = base_devices * quantity
        if effective_plan:
            effective_plan = dict(effective_plan)
            effective_plan["included_seats"] = seat_limit
            effective_plan["max_devices"] = device_limit

    from app.core.seats import allocated_user_count
    seats_used = allocated_user_count(db, organisation_id)
    seat_over_by = max(0, seats_used - int(seat_limit or 0)) if seat_limit else 0

    return {
        "id": item.id,
        "status": item.status,
        "display_status": display_status,
        "billing_interval": item.billing_interval,
        "period_label": period_label,
        "period_value": period_value.isoformat() if period_value else None,
        "billing_ready": billing_ready,
        "provider_available": _stripe_ready(),
        "can_manage_billing": billing_ready,
        "trial_ends_at": item.trial_ends_at.isoformat() if item.trial_ends_at else None,
        "current_period_ends_at": item.current_period_ends_at.isoformat() if item.current_period_ends_at else None,
        "cancel_at_period_end": bool(item.cancel_at_period_end),
        "grace_ends_at": item.grace_ends_at.isoformat() if item.grace_ends_at else None,
        "billing_provider": item.billing_provider,
        "seat_override": item.seat_override,
        "seat_limit": seat_limit,
        "seats_used": seats_used,
        "seat_over_limit": bool(seat_over_by),
        "seat_over_by": seat_over_by,
        "device_limit": device_limit,
        "plan": effective_plan,
    }

def _scheduled_plan_change_payload(db: Session, item: OrganisationSubscription) -> dict | None:
    """Return FAST's pending plan change from the active Stripe schedule, if any.

    FAST creates a schedule only for period-end downgrades. Releasing that
    schedule cancels the pending downgrade while leaving the current paid
    subscription untouched.
    """
    if (
        not item
        or item.billing_provider != "stripe"
        or not item.external_subscription_id
        or not _stripe_ready()
    ):
        return None

    _configure_stripe()
    current_sub = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
    schedule_ref = _obj_get(current_sub, "schedule")
    schedule_id = str(_obj_get(schedule_ref, "id", schedule_ref) or "").strip()
    if not schedule_id:
        return None

    schedule = stripe.SubscriptionSchedule.retrieve(schedule_id)
    status = str(_obj_get(schedule, "status", "") or "").lower()
    if status not in {"active", "not_started"}:
        return None

    current_phase = _obj_get(schedule, "current_phase", {}) or {}
    current_phase_end = _obj_get(current_phase, "end_date")
    phases = list(_obj_get(schedule, "phases", []) or [])

    for phase in phases:
        phase_start = _obj_get(phase, "start_date")
        if current_phase_end is not None and phase_start is not None and int(phase_start) < int(current_phase_end):
            continue

        metadata = dict(_obj_get(phase, "metadata", {}) or {})
        target_plan_id = str(metadata.get("fast_plan_id") or "").strip()
        if not target_plan_id.isdigit():
            continue

        target_plan = db.get(SubscriptionPlan, int(target_plan_id))
        if not target_plan:
            continue

        # The current live plan is authoritative. Ignore a schedule phase that
        # merely repeats the current plan rather than changing it.
        current_plan = _plan_from_live_stripe_price(db, current_sub) or item.plan
        if current_plan and int(current_plan.id) == int(target_plan.id):
            continue

        interval = str(metadata.get("fast_billing_interval") or item.billing_interval or "monthly").lower()
        if interval not in {"monthly", "annual"}:
            interval = "monthly"
        effective_at = _stripe_datetime(phase_start) or _stripe_datetime(current_phase_end)
        return {
            "type": "downgrade",
            "plan": plan_payload(target_plan),
            "billing_interval": interval,
            "effective_at": effective_at.isoformat() if effective_at else None,
        }

    return None


@router.get("/current")
def current_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if user.organisation_id is None:
        return {"subscription": None}

    organisation_id = int(user.organisation_id)
    payload = subscription_payload(db, organisation_id, refresh_provider=True)
    item = db.scalar(
        select(OrganisationSubscription).where(
            OrganisationSubscription.organisation_id == organisation_id
        )
    )
    scheduled_change = None
    if item:
        try:
            scheduled_change = _scheduled_plan_change_payload(db, item)
        except Exception:
            # Billing account access should remain available if Stripe cannot
            # temporarily return schedule details. The normal subscription state
            # is still useful and can be retried on refresh.
            scheduled_change = None
    payload["scheduled_plan_change"] = scheduled_change
    return {"subscription": payload}


@router.get("/public-plans")
def public_plans(db: Session = Depends(get_db)) -> dict:
    plans = db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.active.is_(True)).order_by(SubscriptionPlan.id)).all()
    return {
        "billing_available": _stripe_ready(),
        "billing_mode": "test" if _stripe_secret_key().startswith("sk_test_") else ("live" if _stripe_ready() else "unconfigured"),
        "currency": settings.billing_currency.lower(),
        "supported_sports": [{"key": key, "name": name} for key, name in SUPPORTED_SPORTS],
        "plans": [plan_payload(item) for item in plans],
    }


class PlanRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    monthly_price_pence: int = Field(default=0, ge=0)
    annual_price_pence: int = Field(default=0, ge=0)
    trial_days: int = Field(default=0, ge=0, le=365)
    included_seats: int = Field(default=1, ge=1)
    max_devices: int = Field(default=1, ge=1)
    products: list[str] = Field(default_factory=list)
    sports: list[str] = Field(default_factory=list)
    cloud_storage_gb: int = Field(default=0, ge=0)
    remote_management: bool = False
    priority_support: bool = False
    self_service_upgrades: bool = False
    active: bool = True


@router.get("/plans")
def list_plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="FAST owner access required")
    plans = db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.name)).all()
    return {"plans": [plan_payload(item) for item in plans]}


@router.post("/plans")
def create_plan(payload: PlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="FAST owner access required")
    if db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.name == payload.name.strip())):
        raise HTTPException(status_code=409, detail="A plan with that name already exists")
    item = SubscriptionPlan(
        name=payload.name.strip(), description=payload.description.strip() or None,
        monthly_price_pence=payload.monthly_price_pence, annual_price_pence=payload.annual_price_pence,
        trial_days=payload.trial_days, included_seats=payload.included_seats, max_devices=payload.max_devices,
        products_json=json.dumps(payload.products), sports_json=json.dumps(payload.sports),
        features_json=json.dumps({"remote_management": payload.remote_management, "priority_support": payload.priority_support}),
        cloud_storage_gb=payload.cloud_storage_gb, self_service_upgrades=payload.self_service_upgrades, active=payload.active,
    )
    db.add(item); db.flush()
    db.add(AuditLog(admin_user_id=user.id, action="subscription_plan_created", category="billing", target_type="subscription_plan", target_id=item.id, target_label=item.name, details="Flexible subscription plan created."))
    db.commit(); db.refresh(item)
    return {"plan": plan_payload(item)}


class AssignmentRequest(BaseModel):
    organisation_id: int
    plan_id: int
    status: str = "active"
    billing_interval: str = "monthly"
    seat_override: int | None = Field(default=None, ge=1)


@router.post("/assign")
def assign_plan(payload: AssignmentRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="FAST owner access required")
    organisation = db.get(Organisation, payload.organisation_id)
    plan = db.get(SubscriptionPlan, payload.plan_id)
    if not organisation or not plan:
        raise HTTPException(status_code=404, detail="Organisation or plan not found")
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation.id))
    if not item:
        item = OrganisationSubscription(organisation_id=organisation.id)
        db.add(item)
    item.plan_id = plan.id
    item.status = payload.status if payload.status in {"trial", "active", "past_due", "grace_period", "cancelled", "expired"} else "active"
    item.billing_interval = payload.billing_interval if payload.billing_interval in {"monthly", "annual", "manual"} else "monthly"
    item.seat_override = payload.seat_override
    item.updated_at = datetime.now(timezone.utc)
    effective_seat_limit = max(1, int(payload.seat_override or plan.included_seats or 1))
    organisation.subscription_tier = plan.name
    organisation.max_seats = effective_seat_limit
    # Keep the organisation's licence-backed desktop entitlements in lock-step
    # with an administrative plan assignment.  The Launcher authenticates
    # against Licence rows, so changing only the subscription row leaves stale
    # Starter products/device limits after a Starter -> Professional upgrade.
    _ensure_subscription_entitlements(
        db, organisation, plan, quantity=1, seat_limit=effective_seat_limit
    )
    db.add(AuditLog(admin_user_id=user.id, action="subscription_assigned", category="billing", target_type="organisation", target_id=organisation.id, target_label=organisation.name, details=f"Assigned {plan.name} ({item.billing_interval})."))
    db.commit()
    return {"subscription": subscription_payload(db, organisation.id)}


class PublicCheckoutRequest(BaseModel):
    plan_id: int
    billing_interval: str = "monthly"
    organisation_name: str = Field(min_length=2, max_length=180)
    contact_name: str = Field(min_length=1, max_length=160)
    contact_email: str = Field(min_length=5, max_length=320)
    sport: str = Field(default="football", max_length=80)


@router.post("/public-checkout")
def create_public_checkout_session(
    payload: PublicCheckoutRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")

    limiter.enforce(
        f"public-checkout:{client_address(request)}",
        RateLimit(10, 3600),
    )
    email = _normalise_email(payload.contact_email)
    organisation_name = payload.organisation_name.strip()
    contact_name = payload.contact_name.strip()
    sport = _normalise_sport(payload.sport)
    if sport not in SUPPORTED_SPORT_KEYS:
        raise HTTPException(status_code=422, detail="Choose a supported FAST sport")

    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="That email already has a FAST account. Contact FAST to change an existing subscription.")
    if db.scalar(select(Organisation).where(func.lower(Organisation.name) == organisation_name.lower())):
        raise HTTPException(status_code=409, detail="That organisation already exists in FAST Cloud. Contact FAST to manage its subscription.")

    plan = db.get(SubscriptionPlan, payload.plan_id)
    if not plan or not plan.active:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    if str(plan.name or "").strip().lower() not in {"starter", "professional"}:
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")

    interval = payload.billing_interval.lower().strip()
    if interval not in {"monthly", "annual"}:
        raise HTTPException(status_code=422, detail="Billing interval must be monthly or annual")
    amount = plan.monthly_price_pence if interval == "monthly" else plan.annual_price_pence
    if amount <= 0 or not bool(plan.self_service_upgrades):
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")

    price = _stripe_price_for_plan(plan, interval)
    metadata = {
        "fast_public_checkout": "1",
        "fast_plan_id": str(plan.id),
        "fast_billing_interval": interval,
        "fast_organisation_name": organisation_name,
        "fast_contact_name": contact_name,
        "fast_contact_email": email,
        "fast_sport": sport,
    }
    _configure_stripe()
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": str(_obj_get(price, "id")), "quantity": 1}],
            customer_email=email,
            success_url=f"{settings.public_app_url.rstrip('/')}/pricing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.public_app_url.rstrip('/')}/pricing?checkout=cancelled",
            metadata=metadata,
            subscription_data={"metadata": metadata},
            allow_promotion_codes=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe Checkout could not be created: {exc}") from exc
    return {"url": _obj_get(session, "url"), "session_id": _obj_get(session, "id")}


class CheckoutRequest(BaseModel):
    plan_id: int
    billing_interval: str = "monthly"


@router.post("/checkout")
def create_checkout_session(payload: CheckoutRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")
    plan = db.get(SubscriptionPlan, payload.plan_id)
    if not plan or not plan.active:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    interval = payload.billing_interval.lower().strip()
    if interval not in {"monthly", "annual"}:
        raise HTTPException(status_code=422, detail="Billing interval must be monthly or annual")
    amount = plan.monthly_price_pence if interval == "monthly" else plan.annual_price_pence
    if amount <= 0 or not bool(plan.self_service_upgrades):
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")

    organisation = db.get(Organisation, organisation_id)
    current = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if current and current.external_subscription_id and str(current.status).lower() not in {"cancelled", "expired"}:
        raise HTTPException(status_code=409, detail="This organisation already has a Stripe subscription. Use Manage subscription instead.")

    price = _stripe_price_for_plan(plan, interval)
    customer_id = current.external_customer_id if current and current.external_customer_id else None
    customer_email = organisation.contact_email or user.email
    metadata = {"fast_organisation_id": str(organisation_id), "fast_plan_id": str(plan.id), "fast_billing_interval": interval}
    params = {
        "mode": "subscription",
        "line_items": [{"price": str(_obj_get(price, "id")), "quantity": 1}],
        "success_url": f"{settings.public_app_url.rstrip('/')}/pricing?checkout=success",
        "cancel_url": f"{settings.public_app_url.rstrip('/')}/pricing?checkout=cancelled",
        "client_reference_id": str(organisation_id),
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        "allow_promotion_codes": True,
    }
    if plan.trial_days > 0:
        params["subscription_data"]["trial_period_days"] = plan.trial_days
    if customer_id:
        params["customer"] = customer_id
    else:
        params["customer_email"] = customer_email
    try:
        session = stripe.checkout.Session.create(**params)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe Checkout could not be created: {exc}") from exc
    return {"url": _obj_get(session, "url"), "session_id": _obj_get(session, "id")}


class ChangePlanRequest(BaseModel):
    plan_id: int
    billing_interval: str = "monthly"
    proration_date: int | None = None


def _invoice_line_is_proration(line) -> bool:
    legacy = _obj_get(line, "proration")
    if legacy is not None:
        return bool(legacy)
    parent = _obj_get(line, "parent", {}) or {}
    details = _obj_get(parent, "subscription_item_details", {}) or {}
    return bool(_obj_get(details, "proration", False))


def _preview_plan_change_invoice(current_sub, subscription_item_id: str, target_price_id: str, quantity: int, proration_date: int):
    """Ask Stripe for a non-mutating preview of the proposed upgrade invoice.

    Stripe's Create Preview Invoice API is the source of truth for proration.
    Passing the same proration timestamp into the real subscription update keeps
    the confirmed estimate and the eventual charge aligned.
    """
    params = {
        "subscription": str(_obj_get(current_sub, "id", "") or ""),
        "subscription_details": {
            "items": [{"id": subscription_item_id, "price": target_price_id, "quantity": quantity}],
            "proration_date": proration_date,
            "proration_behavior": "always_invoice",
        },
    }
    customer = str(_obj_get(_obj_get(current_sub, "customer"), "id", _obj_get(current_sub, "customer", "")) or "").strip()
    if customer:
        params["customer"] = customer
    try:
        return stripe.Invoice.create_preview(**params)
    except AttributeError as exc:
        raise HTTPException(status_code=503, detail="This FAST Cloud deployment needs a newer Stripe SDK before plan-change previews can be used") from exc


@router.post("/change-plan/preview")
def preview_subscription_plan_change(payload: ChangePlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if not item or item.billing_provider != "stripe" or not item.external_subscription_id:
        raise HTTPException(status_code=409, detail="This organisation does not have an active Stripe subscription")
    target = db.get(SubscriptionPlan, payload.plan_id)
    if not target or not target.active:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    if not target.self_service_upgrades:
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")
    interval = payload.billing_interval.lower().strip()
    if interval not in {"monthly", "annual"}:
        raise HTTPException(status_code=422, detail="Billing interval must be monthly or annual")

    target_price = _stripe_price_for_plan(target, interval)
    _configure_stripe()
    try:
        current_sub = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        sub_items = _subscription_items(current_sub)
        if not sub_items:
            raise HTTPException(status_code=409, detail="Stripe subscription has no billable item")
        first_item = sub_items[0]
        subscription_item_id = str(_obj_get(first_item, "id", "") or "")
        current_plan = _plan_from_live_stripe_price(db, current_sub) or (db.get(SubscriptionPlan, item.plan_id) if item.plan_id else None)
        current_interval = _subscription_billing_interval(current_sub, item.billing_interval)
        if current_plan and current_plan.id == target.id and current_interval == interval:
            return {"change": "unchanged", "effective": "now", "target_plan": plan_payload(target)}

        current_amount = 0
        if current_plan:
            current_amount = current_plan.monthly_price_pence if current_interval == "monthly" else current_plan.annual_price_pence
        target_amount = target.monthly_price_pence if interval == "monthly" else target.annual_price_pence
        is_downgrade = bool(current_plan and target_amount < current_amount)
        period_end = _subscription_period_end(current_sub)
        common = {
            "change": "downgrade" if is_downgrade else "upgrade",
            "effective": "period_end" if is_downgrade else "now",
            "effective_at": period_end.isoformat() if is_downgrade and period_end else None,
            "current_plan": plan_payload(current_plan) if current_plan else None,
            "target_plan": plan_payload(target),
            "current_billing_interval": current_interval,
            "target_billing_interval": interval,
            "next_renewal_at": period_end.isoformat() if period_end else None,
            "next_renewal_amount_pence": target_amount,
            "currency": settings.billing_currency.lower(),
        }
        if is_downgrade:
            return {**common, "amount_due_now_pence": 0, "credit_pence": 0, "upgrade_charge_pence": 0, "proration_date": None}

        proration_date = int(datetime.now(timezone.utc).timestamp())
        quantity = max(1, int(_obj_get(first_item, "quantity", 1) or 1))
        preview = _preview_plan_change_invoice(
            current_sub,
            subscription_item_id,
            str(_obj_get(target_price, "id")),
            quantity,
            proration_date,
        )
        lines = list(_obj_get(_obj_get(preview, "lines", {}), "data", []) or [])
        proration_lines = [line for line in lines if _invoice_line_is_proration(line)]
        credit = sum(abs(min(0, int(_obj_get(line, "amount", 0) or 0))) for line in proration_lines)
        charge = sum(max(0, int(_obj_get(line, "amount", 0) or 0)) for line in proration_lines)
        proration_total = charge - credit
        amount_due = max(0, proration_total)
        if not proration_lines:
            amount_due = max(0, int(_obj_get(preview, "amount_due", 0) or 0))
        return {
            **common,
            "amount_due_now_pence": amount_due,
            "credit_pence": credit,
            "upgrade_charge_pence": charge,
            "proration_date": proration_date,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe could not preview this plan change: {exc}") from exc


@router.post("/change-plan")
def change_subscription_plan(payload: ChangePlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Change an existing Stripe subscription without creating a second subscription.

    Upgrades are applied immediately and Stripe prorates the remaining period.
    Downgrades are scheduled for the next renewal so paid access is retained.
    """
    organisation_id = _require_org_admin(user)
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if not item or item.billing_provider != "stripe" or not item.external_subscription_id:
        raise HTTPException(status_code=409, detail="This organisation does not have an active Stripe subscription")
    target = db.get(SubscriptionPlan, payload.plan_id)
    if not target or not target.active:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    if not target.self_service_upgrades:
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")
    interval = payload.billing_interval.lower().strip()
    if interval not in {"monthly", "annual"}:
        raise HTTPException(status_code=422, detail="Billing interval must be monthly or annual")
    target_price = _stripe_price_for_plan(target, interval)
    _configure_stripe()
    try:
        current_sub = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        sub_items = _subscription_items(current_sub)
        if not sub_items:
            raise HTTPException(status_code=409, detail="Stripe subscription has no billable item")
        subscription_item_id = str(_obj_get(sub_items[0], "id", "") or "")
        current_plan = _plan_from_live_stripe_price(db, current_sub) or (db.get(SubscriptionPlan, item.plan_id) if item.plan_id else None)
        if current_plan and current_plan.id == target.id and _subscription_billing_interval(current_sub, item.billing_interval) == interval:
            return {"change": "unchanged", "effective": "now", "subscription": subscription_payload(db, organisation_id)}

        current_amount = 0
        if current_plan:
            current_interval = _subscription_billing_interval(current_sub, item.billing_interval)
            current_amount = current_plan.monthly_price_pence if current_interval == "monthly" else current_plan.annual_price_pence
        target_amount = target.monthly_price_pence if interval == "monthly" else target.annual_price_pence
        is_downgrade = bool(current_plan and target_amount < current_amount)
        metadata = dict(_obj_get(current_sub, "metadata", {}) or {})
        metadata.update({"fast_organisation_id": str(organisation_id), "fast_plan_id": str(target.id), "fast_billing_interval": interval})

        if is_downgrade:
            period_end = _subscription_period_end(current_sub)
            if not period_end:
                raise HTTPException(status_code=409, detail="Stripe did not return the current billing period end")

            # Stripe requires every current/future phase to be supplied when an
            # active Subscription Schedule is updated.  In particular, the
            # current phase needs its original start_date as well as its end_date.
            # Creating a schedule from the live subscription gives us those exact
            # phase boundaries; we then append one target-plan billing cycle and
            # release the subscription so it continues normally on that price.
            schedule = _obj_get(current_sub, "schedule")
            schedule_id = str(_obj_get(schedule, "id", schedule) or "").strip()
            if not schedule_id:
                schedule_obj = stripe.SubscriptionSchedule.create(from_subscription=item.external_subscription_id)
                schedule_id = str(_obj_get(schedule_obj, "id", "") or "").strip()
                if not schedule_id:
                    raise HTTPException(status_code=502, detail="Stripe created a subscription schedule without an id")
            else:
                schedule_obj = stripe.SubscriptionSchedule.retrieve(schedule_id)

            # Retrieve once more after creation so current_phase is populated
            # consistently across Stripe SDK/API versions.
            schedule_obj = stripe.SubscriptionSchedule.retrieve(schedule_id)
            current_phase = _obj_get(schedule_obj, "current_phase", {}) or {}
            current_phase_start = _obj_get(current_phase, "start_date")
            current_phase_end = _obj_get(current_phase, "end_date")
            if current_phase_start is None:
                raise HTTPException(status_code=502, detail="Stripe subscription schedule has no current phase start date")

            phase_end_ts = int(current_phase_end or period_end.timestamp())
            current_price = _obj_get(sub_items[0], "price", {}) or {}
            current_price_id = str(_obj_get(current_price, "id", "") or "").strip()
            target_price_id = str(_obj_get(target_price, "id", "") or "").strip()
            if not current_price_id or not target_price_id:
                raise HTTPException(status_code=409, detail="Stripe subscription price information is incomplete")
            quantity = max(1, int(_obj_get(sub_items[0], "quantity", 1) or 1))

            current_metadata = dict(_obj_get(current_sub, "metadata", {}) or {})
            target_duration_interval = "month" if interval == "monthly" else "year"
            stripe.SubscriptionSchedule.modify(
                schedule_id,
                end_behavior="release",
                proration_behavior="none",
                phases=[
                    {
                        "items": [{"price": current_price_id, "quantity": quantity}],
                        "start_date": int(current_phase_start),
                        "end_date": phase_end_ts,
                        "metadata": current_metadata,
                        "proration_behavior": "none",
                    },
                    {
                        "items": [{"price": target_price_id, "quantity": quantity}],
                        "duration": {"interval": target_duration_interval, "interval_count": 1},
                        "metadata": metadata,
                        "proration_behavior": "none",
                    },
                ],
            )
            db.add(AuditLog(admin_user_id=user.id, action="subscription_downgrade_scheduled", category="billing", target_type="organisation", target_id=organisation_id, target_label=str(organisation_id), details=f"Scheduled {target.name} ({interval}) for next renewal."))
            db.commit()
            return {"change": "downgrade", "effective": "period_end", "effective_at": period_end.isoformat(), "target_plan": plan_payload(target), "subscription": subscription_payload(db, organisation_id)}

        update_params = {
            "items": [{"id": subscription_item_id, "price": str(_obj_get(target_price, "id")), "quantity": max(1, int(_obj_get(sub_items[0], "quantity", 1) or 1))}],
            "metadata": metadata,
            # Upgrades are charged immediately. Stripe credits the unused part
            # of the old plan and invoices only the net proration now.
            "proration_behavior": "always_invoice",
        }
        if payload.proration_date:
            update_params["proration_date"] = int(payload.proration_date)
        updated = stripe.Subscription.modify(item.external_subscription_id, **update_params)
        _sync_stripe_subscription(db, updated, organisation_id_override=organisation_id)
        db.add(AuditLog(admin_user_id=user.id, action="subscription_upgraded", category="billing", target_type="organisation", target_id=organisation_id, target_label=str(organisation_id), details=f"Changed to {target.name} ({interval})."))
        db.commit()
        return {"change": "upgrade", "effective": "now", "target_plan": plan_payload(target), "subscription": subscription_payload(db, organisation_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe subscription could not be changed: {exc}") from exc


@router.post("/change-plan/cancel-scheduled")
def cancel_scheduled_plan_change(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Cancel a pending FAST period-end downgrade and keep the current plan.

    Stripe's schedule ``release`` operation removes future scheduled phases but
    leaves the underlying subscription active on its current price.
    """
    organisation_id = _require_org_admin(user)
    item = db.scalar(
        select(OrganisationSubscription).where(
            OrganisationSubscription.organisation_id == organisation_id
        )
    )
    if not item or item.billing_provider != "stripe" or not item.external_subscription_id:
        raise HTTPException(status_code=409, detail="This organisation does not have an active Stripe subscription")
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")

    _configure_stripe()
    try:
        current_sub = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        pending = _scheduled_plan_change_payload(db, item)
        if not pending:
            raise HTTPException(status_code=409, detail="There is no scheduled FAST downgrade to cancel")

        schedule_ref = _obj_get(current_sub, "schedule")
        schedule_id = str(_obj_get(schedule_ref, "id", schedule_ref) or "").strip()
        if not schedule_id:
            raise HTTPException(status_code=409, detail="There is no active Stripe schedule to cancel")

        # Do not use SubscriptionSchedule.cancel(): Stripe documents that cancel
        # also cancels the underlying subscription. ``release`` stops the future
        # phases while preserving the currently active subscription.
        stripe.SubscriptionSchedule.release(schedule_id)

        refreshed = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        _sync_stripe_subscription(db, refreshed, organisation_id_override=organisation_id)
        db.add(
            AuditLog(
                admin_user_id=user.id,
                action="subscription_downgrade_cancelled",
                category="billing",
                target_type="organisation",
                target_id=organisation_id,
                target_label=str(organisation_id),
                details="Scheduled subscription downgrade cancelled; current plan retained.",
            )
        )
        db.commit()
        return {
            "cancelled": True,
            "message": "Scheduled downgrade cancelled. Your current FAST plan will continue.",
            "subscription": subscription_payload(db, organisation_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe scheduled downgrade could not be cancelled: {exc}") from exc


@router.post("/portal")
def create_portal_session(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if not _stripe_ready() or not item or item.billing_provider != "stripe" or not item.external_customer_id:
        raise HTTPException(status_code=409, detail="Stripe billing is not connected for this organisation")
    _configure_stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=item.external_customer_id,
            return_url=f"{settings.public_app_url.rstrip('/')}/account",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe billing portal could not be opened: {exc}") from exc
    return {"url": _obj_get(session, "url")}



def _invoice_subscription_id(invoice) -> str:
    """Return the subscription ID from both legacy and current Stripe invoice shapes.

    Older Stripe API versions exposed ``invoice.subscription`` directly. Newer
    versions expose the generating subscription through
    ``invoice.parent.subscription_details.subscription``. Supporting both keeps
    payment-failure/recovery handling stable across Stripe API upgrades.
    """
    direct = str(_obj_get(invoice, "subscription", "") or "").strip()
    if direct:
        return direct
    parent = _obj_get(invoice, "parent", {}) or {}
    subscription_details = _obj_get(parent, "subscription_details", {}) or {}
    nested = _obj_get(subscription_details, "subscription", "")
    if nested:
        return str(_obj_get(nested, "id", nested) or "").strip()
    return ""


def _stripe_customer_id(value) -> str:
    customer = _obj_get(value, "customer", "")
    return str(_obj_get(customer, "id", customer) or "").strip()


def _subscription_for_stripe_reference(
    db: Session,
    *,
    subscription_id: str = "",
    customer_id: str = "",
) -> OrganisationSubscription | None:
    if subscription_id:
        item = db.scalar(
            select(OrganisationSubscription).where(
                OrganisationSubscription.external_subscription_id == subscription_id
            )
        )
        if item:
            return item
    if customer_id:
        # A FAST organisation has one commercial subscription. Customer-ID
        # fallback protects invoice processing when Stripe changes where the
        # subscription reference is represented in an event payload.
        return db.scalar(
            select(OrganisationSubscription).where(
                OrganisationSubscription.external_customer_id == customer_id
            )
        )
    return None


def _record_billing_webhook_event(
    db: Session,
    event,
    data,
    *,
    item: OrganisationSubscription | None,
    processing_status: str,
    details: str,
    subscription_id: str = "",
) -> None:
    event_id = str(_obj_get(event, "id", "") or "").strip() or None
    event_type = str(_obj_get(event, "type", "") or "unknown")
    customer_id = _stripe_customer_id(data) or None
    if event_type.startswith("customer.subscription."):
        resolved_subscription_id = subscription_id or str(_obj_get(data, "id", "") or "")
    else:
        resolved_subscription_id = subscription_id or _invoice_subscription_id(data)
    if event_id:
        row = db.scalar(select(BillingWebhookEvent).where(BillingWebhookEvent.external_event_id == event_id))
    else:
        row = None
    if row is None:
        row = BillingWebhookEvent(provider="stripe", external_event_id=event_id, event_type=event_type)
        db.add(row)
    row.event_type = event_type
    row.external_customer_id = customer_id
    row.external_subscription_id = resolved_subscription_id or None
    row.organisation_id = item.organisation_id if item else None
    row.matched = item is not None
    row.processing_status = processing_status
    row.details = details[:2000]


def _apply_payment_failure(db: Session, invoice) -> OrganisationSubscription | None:
    subscription_id = _invoice_subscription_id(invoice)
    customer_id = _stripe_customer_id(invoice)
    item = _subscription_for_stripe_reference(
        db, subscription_id=subscription_id, customer_id=customer_id
    )
    if not item:
        return None

    # Refresh the subscription first so period dates/cancellation state remain
    # current even when the failure event arrives before subscription.updated.
    if subscription_id and _stripe_ready():
        try:
            _configure_stripe()
            remote = stripe.Subscription.retrieve(subscription_id)
            _sync_stripe_subscription(db, remote)
        except Exception:
            # The invoice failure itself is still authoritative enough to place
            # an already-matched FAST subscription into grace.
            pass

    item.status = "grace_period"
    now = datetime.now(timezone.utc)
    grace_candidate = now + timedelta(days=max(1, settings.billing_grace_days))
    # Never shorten an existing grace window on Smart Retry attempts.
    if not item.grace_ends_at or item.grace_ends_at < grace_candidate:
        item.grace_ends_at = grace_candidate
    item.updated_at = now
    return item


def _apply_payment_recovery(db: Session, invoice) -> OrganisationSubscription | None:
    subscription_id = _invoice_subscription_id(invoice)
    customer_id = _stripe_customer_id(invoice)
    item = _subscription_for_stripe_reference(
        db, subscription_id=subscription_id, customer_id=customer_id
    )
    if not item:
        return None
    if subscription_id and _stripe_ready():
        try:
            _configure_stripe()
            remote = stripe.Subscription.retrieve(subscription_id)
            _sync_stripe_subscription(db, remote)
        except Exception:
            pass
    if item.status not in {"trial", "cancelled", "expired"}:
        item.status = "active"
        item.grace_ends_at = None
        item.updated_at = datetime.now(timezone.utc)
    return item

def _stripe_datetime(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OSError):
        return None


def _map_stripe_status(value: str | None) -> str:
    status = str(value or "").lower()
    return {
        "trialing": "trial",
        "active": "active",
        "past_due": "past_due",
        "unpaid": "past_due",
        "canceled": "cancelled",
        "incomplete": "past_due",
        "incomplete_expired": "expired",
        "paused": "grace_period",
    }.get(status, "active")


def _subscription_items(subscription) -> list:
    return list(_obj_get(_obj_get(subscription, "items", {}), "data", []) or [])


def _subscription_price_identity(subscription) -> tuple[str, str]:
    """Return (price_id, lookup_key) for the first recurring Stripe item."""
    items = _subscription_items(subscription)
    if not items:
        return "", ""
    price = _obj_get(items[0], "price", {}) or {}
    return (
        str(_obj_get(price, "id", "") or "").strip(),
        str(_obj_get(price, "lookup_key", "") or "").strip(),
    )


def _plan_from_live_stripe_price(db: Session, subscription) -> SubscriptionPlan | None:
    """Resolve the FAST plan represented by the subscription's live Stripe price.

    Stripe Dashboard price/tier changes preserve the subscription metadata from
    the original checkout.  Therefore metadata cannot be authoritative for a
    later Professional -> Starter (or reverse) switch.
    """
    price_id, lookup_key = _subscription_price_identity(subscription)
    plan_key = None
    if lookup_key:
        for (candidate_plan, candidate_interval), candidate_lookup in _STRIPE_LOOKUP_KEYS.items():
            if lookup_key == candidate_lookup:
                plan_key = candidate_plan
                break
    if plan_key is None and price_id:
        mapped = _STRIPE_PRICE_PLAN_KEYS.get(price_id)
        if mapped:
            plan_key = mapped[0]
    if not plan_key:
        return None
    return db.scalar(
        select(SubscriptionPlan).where(func.lower(SubscriptionPlan.name) == plan_key.lower())
    )


def _subscription_quantity(subscription) -> int:
    """Return the paid Stripe quantity, defaulting safely to one unit."""
    items = _subscription_items(subscription)
    if not items:
        return 1
    try:
        return max(1, int(_obj_get(items[0], "quantity", 1) or 1))
    except (TypeError, ValueError):
        return 1


def _subscription_billing_interval(subscription, fallback: str = "monthly") -> str:
    """Resolve the live billing interval from Stripe rather than stale metadata."""
    items = _subscription_items(subscription)
    if items:
        price = _obj_get(items[0], "price", {}) or {}
        recurring = _obj_get(price, "recurring", {}) or {}
        interval = str(_obj_get(recurring, "interval", "") or "").lower()
        if interval == "year":
            return "annual"
        if interval == "month":
            return "monthly"
    return fallback if fallback in {"monthly", "annual", "manual"} else "monthly"


def _subscription_period_end(subscription) -> datetime | None:
    # Stripe API versions can expose the billing period on the subscription
    # itself or on the first subscription item. Support both shapes.
    direct = _stripe_datetime(_obj_get(subscription, "current_period_end"))
    if direct:
        return direct
    items = _subscription_items(subscription)
    if items:
        return _stripe_datetime(_obj_get(items[0], "current_period_end"))
    return None


def _subscription_cancel_at(subscription) -> datetime | None:
    """Return Stripe's explicit scheduled cancellation timestamp, if present.

    Stripe Billing Portal can represent an end-of-period cancellation with an
    explicit ``cancel_at`` timestamp even when ``cancel_at_period_end`` is false.
    FAST normalises either representation into its existing cancellation flag.
    """
    return _stripe_datetime(_obj_get(subscription, "cancel_at"))


def _subscription_cancellation_scheduled(subscription) -> bool:
    return bool(_obj_get(subscription, "cancel_at_period_end", False) or _subscription_cancel_at(subscription))


def _ensure_subscription_entitlements(
    db: Session, organisation: Organisation, plan: SubscriptionPlan, *, quantity: int = 1, seat_limit: int | None = None
) -> None:
    """Materialise plan entitlements as the organisation's managed club licence.

    Desktop authentication/device activation is licence-backed, so a paid
    subscription must create/update that licence rather than only changing the
    subscription row. This helper is idempotent and also repairs subscriptions
    created before subscription-backed provisioning was added.
    """
    products = _loads(plan.products_json, [])
    plan_sports = _loads(plan.sports_json, [])
    # Preserve the organisation's purchased sport across Stripe resyncs/tier
    # changes. A plan sport acts as a default only when the organisation has not
    # already selected one.
    organisation_sports = _loads(organisation.sports_json, [])
    selected_sports = organisation_sports or plan_sports

    quantity = max(1, int(quantity or 1))
    base_seats = max(1, int(plan.included_seats or 1))
    base_devices = max(1, int(plan.max_devices or 1))
    if seat_limit is None:
        licensed_users = base_seats * quantity
        capacity_multiplier = quantity
    else:
        licensed_users = max(1, int(seat_limit))
        capacity_multiplier = max(1, (licensed_users + base_seats - 1) // base_seats)
    licensed_devices = base_devices * capacity_multiplier

    organisation.subscription_tier = plan.name
    organisation.max_seats = licensed_users
    organisation.sports_json = json.dumps(selected_sports)

    club = db.scalar(select(Club).where(Club.organisation_id == organisation.id).order_by(Club.id))
    if not club:
        base_name = organisation.name.strip() or f"Organisation {organisation.id}"
        club_name = base_name
        suffix = 2
        while db.scalar(select(Club).where(func.lower(Club.name) == club_name.lower())):
            club_name = f"{base_name} {suffix}"
            suffix += 1
        club = Club(name=club_name, organisation_id=organisation.id, status="active")
        db.add(club)
        db.flush()

    # An organisation can have historical/multiple club records.  Older FAST
    # builds provisioned the desktop licence independently of subscriptions, so
    # updating only the first club/latest licence can leave the licence actually
    # used by Launcher on the old tier.  Synchronise every current club-owned
    # licence for this organisation, while still creating one when none exists.
    # Resolve the concrete club ids first, then target licence rows directly.
    # This mirrors /licenses/current and avoids relying on an ORM join path when
    # repairing an already-provisioned organisation licence.
    organisation_club_ids = list(
        db.scalars(
            select(Club.id)
            .where(Club.organisation_id == organisation.id)
            .order_by(Club.id)
        ).all()
    )
    if club.id not in organisation_club_ids:
        organisation_club_ids.append(club.id)

    organisation_licences = db.scalars(
        select(Licence)
        .where(
            Licence.club_id.in_(organisation_club_ids),
            Licence.owner_type == "club",
        )
        .order_by(Licence.id.desc())
    ).all()
    if not organisation_licences:
        code = generate_licence_code(plan.name)
        licence = Licence(
            code_hash=hash_licence_code(code),
            code_last_four=normalise_licence_code(code)[-4:],
            tier=plan.name,
            owner_type="club",
            club_id=club.id,
            status="active",
            activated_at=datetime.now(timezone.utc),
        )
        db.add(licence)
        organisation_licences = [licence]

    for licence in organisation_licences:
        licence.tier = plan.name
        licence.products_json = json.dumps(products)
        licence.sports_json = json.dumps(selected_sports)
        licence.features_json = plan.features_json or "{}"
        licence.max_devices = licensed_devices
        licence.max_users = licensed_users
        licence.status = "active"
        licence.renewable = True

    # Flush the licence writes before the subscription assignment response is
    # produced.  This also makes failures visible in /docs immediately instead
    # of leaving the organisation tier updated while the desktop licence stays
    # stale.
    db.flush()

    # Keep organisation users inside the subscription envelope. Their explicit
    # assignment can narrow access later, but a newly provisioned administrator
    # must receive the plan products/sports immediately.
    users = db.scalars(select(User).where(User.organisation_id == organisation.id)).all()
    for user in users:
        if str(user.role or "").lower() == "administrator":
            user.products_json = json.dumps(products)
            user.sports_json = json.dumps(selected_sports)
        membership = db.scalar(select(ClubMember).where(ClubMember.club_id == club.id, ClubMember.user_id == user.id))
        if not membership:
            db.add(ClubMember(club_id=club.id, user_id=user.id, role=str(user.role or "analyst").lower()))


def _sync_stripe_subscription(
    db: Session,
    subscription,
    *,
    organisation_id_override: int | None = None,
) -> None:
    metadata = _obj_get(subscription, "metadata", {}) or {}
    metadata_organisation_id = str(_obj_get(metadata, "fast_organisation_id", "") or "")
    plan_id = str(_obj_get(metadata, "fast_plan_id", "") or "")
    if organisation_id_override is not None:
        organisation_id = str(int(organisation_id_override))
    else:
        organisation_id = metadata_organisation_id
    if not organisation_id.isdigit():
        return
    organisation = db.get(Organisation, int(organisation_id))
    if not organisation:
        return
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation.id))
    if not item:
        item = OrganisationSubscription(organisation_id=organisation.id)
        db.add(item)
    # The live Stripe price is authoritative for tier changes. Dashboard
    # changes do not rewrite checkout metadata, so relying on fast_plan_id would
    # leave a downgraded Starter subscription provisioned as Professional.
    effective_plan = _plan_from_live_stripe_price(db, subscription)
    if effective_plan:
        item.plan_id = effective_plan.id
    elif plan_id.isdigit():
        effective_plan = db.get(SubscriptionPlan, int(plan_id))
        if effective_plan:
            item.plan_id = effective_plan.id
    if effective_plan is None and item.plan_id:
        effective_plan = db.get(SubscriptionPlan, int(item.plan_id))

    mapped_status = _map_stripe_status(_obj_get(subscription, "status"))
    if mapped_status == "past_due":
        item.status = "grace_period"
        if not item.grace_ends_at:
            item.grace_ends_at = datetime.now(timezone.utc) + timedelta(days=max(1, settings.billing_grace_days))
    else:
        item.status = mapped_status
        if mapped_status in {"active", "trial"}:
            item.grace_ends_at = None
    metadata_interval = str(_obj_get(metadata, "fast_billing_interval", item.billing_interval or "monthly") or "monthly")
    quantity = _subscription_quantity(subscription)
    item.billing_interval = _subscription_billing_interval(subscription, metadata_interval)
    item.billing_provider = "stripe"
    item.external_customer_id = str(_obj_get(subscription, "customer", "") or item.external_customer_id or "") or None
    item.external_subscription_id = str(_obj_get(subscription, "id", "") or item.external_subscription_id or "") or None
    item.trial_ends_at = _stripe_datetime(_obj_get(subscription, "trial_end"))
    period_end = _subscription_period_end(subscription)
    cancel_at = _subscription_cancel_at(subscription)
    cancellation_scheduled = _subscription_cancellation_scheduled(subscription)
    # Normalise both Stripe cancellation representations into FAST's existing
    # cancel-at-period-end flag. When Stripe supplies an explicit cancel_at
    # timestamp, use it as the access-end date if it is earlier than the normal
    # billing period end. This keeps entitlement expiry and customer-facing
    # wording aligned with the Billing Portal.
    item.cancel_at_period_end = cancellation_scheduled
    if cancellation_scheduled and cancel_at and (period_end is None or cancel_at < period_end):
        item.current_period_ends_at = cancel_at
    else:
        item.current_period_ends_at = period_end
    item.updated_at = datetime.now(timezone.utc)
    if effective_plan:
        organisation.subscription_tier = effective_plan.name
        # Stripe quantity is the paid capacity multiplier. Store the resulting
        # user-seat allowance as the subscription override because the shared
        # seat evaluator otherwise falls back to the plan's single-unit limit.
        item.seat_override = max(1, int(effective_plan.included_seats or 1)) * quantity
        organisation.max_seats = item.seat_override
        # Keep the organisation/admin UI and the licence-backed desktop access
        # in lock-step with Stripe on every subscription sync.  This also makes
        # a resent webhook repair organisations created by older deployments.
        organisation.expires_at = item.current_period_ends_at
        _ensure_subscription_entitlements(db, organisation, effective_plan, quantity=quantity)
        for club in organisation.clubs:
            for licence in club.licences:
                if licence.status == "active":
                    licence.expires_at = item.current_period_ends_at


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    if not _stripe_ready(webhook=True):
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    _configure_stripe()
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=_stripe_webhook_secret())
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook") from exc

    event_type = str(_obj_get(event, "type", ""))
    data = _obj_get(_obj_get(event, "data", {}), "object", {})
    with SessionLocal() as db:
        matched_item = None
        processing_status = "processed"
        details = "Stripe webhook processed."
        referenced_subscription_id = ""
        try:
            if event_type == "checkout.session.completed":
                subscription_id = str(_obj_get(data, "subscription", "") or "")
                referenced_subscription_id = subscription_id
                if subscription_id:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    session_metadata = _obj_get(data, "metadata", {}) or {}
                    if str(_obj_get(session_metadata, "fast_public_checkout", "")) == "1":
                        _provision_public_checkout(db, data, subscription)
                    else:
                        _sync_stripe_subscription(db, subscription)
                    matched_item = _subscription_for_stripe_reference(
                        db,
                        subscription_id=subscription_id,
                        customer_id=_stripe_customer_id(subscription),
                    )
                    details = "Checkout completed and FAST subscription synchronised."
                else:
                    processing_status = "ignored"
                    details = "Checkout completed without a subscription reference."
            elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
                referenced_subscription_id = str(_obj_get(data, "id", "") or "")
                # Billing Portal changes can be followed by multiple Stripe events.
                # For create/update events, fetch the subscription's current state
                # from Stripe before syncing so cancel_at_period_end and period-end
                # changes cannot be overwritten by an older event payload arriving
                # out of order. Deleted events must use their terminal event payload
                # because the remote subscription may no longer be retrievable.
                sync_source = data
                if event_type != "customer.subscription.deleted" and referenced_subscription_id:
                    try:
                        sync_source = stripe.Subscription.retrieve(referenced_subscription_id)
                    except Exception:
                        sync_source = data
                _sync_stripe_subscription(db, sync_source)
                matched_item = _subscription_for_stripe_reference(
                    db,
                    subscription_id=referenced_subscription_id,
                    customer_id=_stripe_customer_id(sync_source),
                )
                if matched_item:
                    if event_type == "customer.subscription.deleted":
                        # A deleted Stripe subscription is terminal: the paid period has
                        # already ended (or the subscription was cancelled immediately).
                        # Do not retain the previous current_period_end here, otherwise
                        # the access evaluator can incorrectly interpret a final deletion
                        # as "cancelled pending" and keep FAST applications enabled.
                        matched_item.status = "cancelled"
                        matched_item.cancel_at_period_end = False
                        matched_item.current_period_ends_at = None
                        matched_item.grace_ends_at = None
                        matched_item.updated_at = datetime.now(timezone.utc)
                        details = "Stripe subscription deleted; FAST access is cancelled immediately."
                    else:
                        details = (
                            f"Subscription state synchronised to {matched_item.status}; "
                            f"cancel_at_period_end={bool(matched_item.cancel_at_period_end)}."
                        )
                else:
                    processing_status = "unmatched"
                    details = "Stripe subscription is not mapped to a FAST organisation."
            elif event_type in {"invoice.payment_failed", "invoice.payment_action_required"}:
                referenced_subscription_id = _invoice_subscription_id(data)
                matched_item = _apply_payment_failure(db, data)
                if matched_item:
                    details = (
                        f"Payment failure applied; FAST access remains available during grace until "
                        f"{matched_item.grace_ends_at.isoformat() if matched_item.grace_ends_at else 'not set'}."
                    )
                else:
                    processing_status = "unmatched"
                    details = (
                        "Payment failure received but no FAST subscription matched the Stripe "
                        f"subscription/customer reference (subscription={referenced_subscription_id or 'none'}, "
                        f"customer={_stripe_customer_id(data) or 'none'})."
                    )
            elif event_type in {"invoice.paid", "invoice.payment_succeeded"}:
                referenced_subscription_id = _invoice_subscription_id(data)
                matched_item = _apply_payment_recovery(db, data)
                if matched_item:
                    details = "Invoice paid; FAST subscription restored to active and grace cleared."
                else:
                    processing_status = "unmatched"
                    details = "Paid invoice received but no FAST subscription matched the Stripe references."
            else:
                processing_status = "ignored"
                details = "Event type is not used by FAST subscription lifecycle handling."

            _record_billing_webhook_event(
                db,
                event,
                data,
                item=matched_item,
                processing_status=processing_status,
                details=details,
                subscription_id=referenced_subscription_id,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            # Persist a diagnostic row in a clean transaction where possible,
            # then return a non-2xx response so Stripe retries transient errors.
            try:
                _record_billing_webhook_event(
                    db,
                    event,
                    data,
                    item=matched_item,
                    processing_status="error",
                    details=f"Webhook processing error: {type(exc).__name__}: {exc}",
                    subscription_id=referenced_subscription_id,
                )
                db.commit()
            except Exception:
                db.rollback()
            raise
    return {"received": True}
