from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models import AuditLog, Organisation, OrganisationSubscription, SubscriptionPlan, User

try:
    import stripe
except ImportError:  # Billing remains safely unavailable until dependency is installed.
    stripe = None

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
settings = get_settings()


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


def _stripe_ready(*, webhook: bool = False) -> bool:
    if stripe is None or not settings.stripe_secret_key:
        return False
    return bool(settings.stripe_webhook_secret) if webhook else True


def _configure_stripe() -> None:
    if stripe is not None:
        stripe.api_key = settings.stripe_secret_key


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


def subscription_payload(db: Session, organisation_id: int) -> dict:
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
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
        }
    status = str(item.status or "unconfigured").lower()
    period_value = item.trial_ends_at if status == "trial" else item.current_period_ends_at
    period_label = "Trial ends" if status == "trial" else ("Access ends" if item.cancel_at_period_end else "Renews")
    billing_ready = bool(item.billing_provider == "stripe" and item.external_customer_id and _stripe_ready())
    return {
        "id": item.id,
        "status": item.status,
        "display_status": str(item.status or "unconfigured").replace("_", " ").title(),
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
        "plan": plan_payload(item.plan),
    }


@router.get("/current")
def current_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if user.organisation_id is None:
        return {"subscription": None}
    return {"subscription": subscription_payload(db, int(user.organisation_id))}


@router.get("/public-plans")
def public_plans(db: Session = Depends(get_db)) -> dict:
    plans = db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.active.is_(True)).order_by(SubscriptionPlan.id)).all()
    return {
        "billing_available": _stripe_ready(),
        "billing_mode": "test" if str(settings.stripe_secret_key).startswith("sk_test_") else ("live" if _stripe_ready() else "unconfigured"),
        "currency": settings.billing_currency.lower(),
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
    organisation.subscription_tier = plan.name
    organisation.max_seats = payload.seat_override or plan.included_seats
    db.add(AuditLog(admin_user_id=user.id, action="subscription_assigned", category="billing", target_type="organisation", target_id=organisation.id, target_label=organisation.name, details=f"Assigned {plan.name} ({item.billing_interval})."))
    db.commit()
    return {"subscription": subscription_payload(db, organisation.id)}


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

    _configure_stripe()
    customer_id = current.external_customer_id if current and current.external_customer_id else None
    customer_email = organisation.contact_email or user.email
    metadata = {"fast_organisation_id": str(organisation_id), "fast_plan_id": str(plan.id), "fast_billing_interval": interval}
    params = {
        "mode": "subscription",
        "line_items": [{
            "price_data": {
                "currency": settings.billing_currency.lower(),
                "unit_amount": amount,
                "recurring": {"interval": "month" if interval == "monthly" else "year"},
                "product_data": {"name": f"FAST {plan.name}", "description": plan.description or "FAST Sports Analytics subscription"},
            },
            "quantity": 1,
        }],
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
            return_url=f"{settings.public_app_url.rstrip('/')}/pricing",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe billing portal could not be opened: {exc}") from exc
    return {"url": _obj_get(session, "url")}


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


def _sync_stripe_subscription(db: Session, subscription) -> None:
    metadata = _obj_get(subscription, "metadata", {}) or {}
    organisation_id = str(_obj_get(metadata, "fast_organisation_id", "") or "")
    plan_id = str(_obj_get(metadata, "fast_plan_id", "") or "")
    if not organisation_id.isdigit():
        return
    organisation = db.get(Organisation, int(organisation_id))
    if not organisation:
        return
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation.id))
    if not item:
        item = OrganisationSubscription(organisation_id=organisation.id)
        db.add(item)
    if plan_id.isdigit() and db.get(SubscriptionPlan, int(plan_id)):
        item.plan_id = int(plan_id)
    item.status = _map_stripe_status(_obj_get(subscription, "status"))
    item.billing_interval = str(_obj_get(metadata, "fast_billing_interval", item.billing_interval or "monthly"))
    item.billing_provider = "stripe"
    item.external_customer_id = str(_obj_get(subscription, "customer", "") or item.external_customer_id or "") or None
    item.external_subscription_id = str(_obj_get(subscription, "id", "") or item.external_subscription_id or "") or None
    item.trial_ends_at = _stripe_datetime(_obj_get(subscription, "trial_end"))
    item.current_period_ends_at = _stripe_datetime(_obj_get(subscription, "current_period_end"))
    item.cancel_at_period_end = bool(_obj_get(subscription, "cancel_at_period_end", False))
    item.updated_at = datetime.now(timezone.utc)
    if item.plan:
        organisation.subscription_tier = item.plan.name
        organisation.max_seats = item.seat_override or item.plan.included_seats


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    if not _stripe_ready(webhook=True):
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    _configure_stripe()
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=settings.stripe_webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook") from exc

    event_type = str(_obj_get(event, "type", ""))
    data = _obj_get(_obj_get(event, "data", {}), "object", {})
    with SessionLocal() as db:
        if event_type == "checkout.session.completed":
            subscription_id = _obj_get(data, "subscription")
            if subscription_id:
                try:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    _sync_stripe_subscription(db, subscription)
                except Exception:
                    db.rollback()
                    raise
        elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
            _sync_stripe_subscription(db, data)
        elif event_type in {"invoice.payment_failed", "invoice.payment_action_required"}:
            subscription_id = str(_obj_get(data, "subscription", "") or "")
            if subscription_id:
                item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.external_subscription_id == subscription_id))
                if item:
                    item.status = "grace_period"
                    item.grace_ends_at = datetime.now(timezone.utc) + timedelta(days=max(1, settings.billing_grace_days))
                    item.updated_at = datetime.now(timezone.utc)
        elif event_type == "invoice.paid":
            subscription_id = str(_obj_get(data, "subscription", "") or "")
            if subscription_id:
                item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.external_subscription_id == subscription_id))
                if item and item.status not in {"trial", "cancelled", "expired"}:
                    item.status = "active"
                    item.grace_ends_at = None
                    item.updated_at = datetime.now(timezone.utc)
        db.commit()
    return {"received": True}
