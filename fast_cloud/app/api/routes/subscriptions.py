from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AuditLog, Organisation, OrganisationSubscription, SubscriptionPlan, User
from app.core.seats import allocated_user_count
from app.core.subscription_access import evaluate_subscription

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _loads(value: str | None, fallback):
    try:
        result = json.loads(value or "")
        return result if isinstance(result, type(fallback)) else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


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
        }
    status = str(item.status or "unconfigured").lower()
    access = evaluate_subscription(item)
    period_value = item.trial_ends_at if status == "trial" else item.current_period_ends_at
    period_label = "Trial ends" if status == "trial" else ("Access ends" if item.cancel_at_period_end else "Renews")
    return {
        "id": item.id,
        "status": item.status,
        "display_status": str(item.status or "unconfigured").replace("_", " ").title(),
        "billing_interval": item.billing_interval,
        "period_label": period_label,
        "period_value": period_value.isoformat() if period_value else None,
        "billing_ready": bool(item.billing_provider and item.billing_provider != "manual"),
        "trial_ends_at": item.trial_ends_at.isoformat() if item.trial_ends_at else None,
        "current_period_ends_at": item.current_period_ends_at.isoformat() if item.current_period_ends_at else None,
        "cancel_at_period_end": bool(item.cancel_at_period_end),
        "grace_ends_at": item.grace_ends_at.isoformat() if item.grace_ends_at else None,
        "billing_provider": item.billing_provider,
        "seat_override": item.seat_override,
        "plan": plan_payload(item.plan),
        "access": access.payload(),
    }


@router.get("/current")
def current_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if user.organisation_id is None:
        return {"subscription": None}
    return {"subscription": subscription_payload(db, int(user.organisation_id))}


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
    trial_ends_at: datetime | None = None
    current_period_ends_at: datetime | None = None
    grace_ends_at: datetime | None = None
    cancel_at_period_end: bool = False
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
    same_plan = bool(item.id and item.plan_id == plan.id)
    # Preserve the current capacity when the existing subscription is being
    # edited without an explicit seat override.  This keeps status-only changes
    # (such as active -> suspended -> active) independent from seat validation.
    preserve_custom_capacity = payload.seat_override is None and plan.name.strip().lower() == "custom"
    if (same_plan and payload.seat_override is None) or preserve_custom_capacity:
        # Custom is an organisation-specific entitlement. Selecting it without a
        # seat override must preserve the organisation's licensed capacity rather
        # than applying the generic Custom plan template (normally 1 seat).
        new_seat_limit = int(organisation.max_seats or plan.included_seats or 1)
        effective_override = item.seat_override if same_plan else new_seat_limit
    else:
        new_seat_limit = int(payload.seat_override or plan.included_seats or 1)
        effective_override = payload.seat_override
    allocated_seats = allocated_user_count(db, organisation.id)
    if new_seat_limit < allocated_seats:
        raise HTTPException(status_code=409, detail=f"Cannot assign a plan with {new_seat_limit} seats while {allocated_seats} user seats are allocated")
    previous_limit = int(organisation.max_seats or 1)
    previous_status = str(item.status or "unconfigured")
    previous_trial_end = item.trial_ends_at
    previous_period_end = item.current_period_ends_at
    previous_grace_end = item.grace_ends_at
    previous_cancel_at_period_end = bool(item.cancel_at_period_end)
    item.plan_id = plan.id
    item.status = payload.status if payload.status in {"trial", "active", "past_due", "grace_period", "cancelled", "suspended", "expired"} else "active"
    item.trial_ends_at = payload.trial_ends_at
    item.current_period_ends_at = payload.current_period_ends_at
    item.grace_ends_at = payload.grace_ends_at
    item.cancel_at_period_end = bool(payload.cancel_at_period_end)
    if item.status == "trial" and item.trial_ends_at is None:
        raise HTTPException(status_code=422, detail="Trial subscriptions require a trial end date")
    if item.status in {"past_due", "grace_period"} and item.grace_ends_at is None and item.current_period_ends_at is None:
        raise HTTPException(status_code=422, detail="Past-due/grace subscriptions require a grace or period end date")
    if (item.status == "cancelled" or item.cancel_at_period_end) and item.current_period_ends_at is None:
        raise HTTPException(status_code=422, detail="Cancelled subscriptions require a current period end date")
    item.billing_interval = payload.billing_interval if payload.billing_interval in {"monthly", "annual", "manual"} else "monthly"
    item.seat_override = effective_override
    item.updated_at = datetime.now(timezone.utc)
    organisation.subscription_tier = plan.name
    organisation.max_seats = new_seat_limit
    db.add(AuditLog(admin_user_id=user.id, action="subscription_assigned", category="billing", target_type="organisation", target_id=organisation.id, target_label=organisation.name, details=f"Assigned {plan.name} ({item.billing_interval}); user seats {new_seat_limit}."))
    if (previous_status != item.status or previous_trial_end != item.trial_ends_at or previous_period_end != item.current_period_ends_at or previous_grace_end != item.grace_ends_at or previous_cancel_at_period_end != bool(item.cancel_at_period_end)):
        db.add(AuditLog(admin_user_id=user.id, action="subscription_lifecycle_changed", category="billing", target_type="organisation", target_id=organisation.id, target_label=organisation.name, details=(
            f"Subscription lifecycle changed: status {previous_status} -> {item.status}; "
            f"trial end {previous_trial_end or 'not set'} -> {item.trial_ends_at or 'not set'}; "
            f"period end {previous_period_end or 'not set'} -> {item.current_period_ends_at or 'not set'}; "
            f"grace end {previous_grace_end or 'not set'} -> {item.grace_ends_at or 'not set'}; "
            f"cancel at period end {previous_cancel_at_period_end} -> {bool(item.cancel_at_period_end)}."
        )))
    if previous_limit != new_seat_limit:
        db.add(AuditLog(admin_user_id=user.id, action="seat_limit_changed", category="billing", target_type="organisation", target_id=organisation.id, target_label=organisation.name, details=f"User seat limit changed from {previous_limit} to {new_seat_limit} by subscription assignment."))
    db.commit()
    return {"subscription": subscription_payload(db, organisation.id)}
