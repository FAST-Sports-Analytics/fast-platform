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
