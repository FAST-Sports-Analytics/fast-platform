from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OrganisationSubscription


ALLOWING_STATUSES = {"active", "trial"}
WARNING_STATUSES = {"past_due", "grace_period", "cancelled"}
BLOCKING_STATUSES = {"suspended", "expired"}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class SubscriptionAccess:
    status: str
    allowed: bool
    warning: bool
    reason: str
    message: str
    access_ends_at: datetime | None = None

    def payload(self) -> dict:
        return {
            "status": self.status,
            "allowed": self.allowed,
            "warning": self.warning,
            "reason": self.reason,
            "message": self.message,
            "access_ends_at": self.access_ends_at.isoformat() if self.access_ends_at else None,
        }


def evaluate_subscription(item: OrganisationSubscription | None, *, now: datetime | None = None) -> SubscriptionAccess:
    """Resolve the effective commercial access state for an organisation.

    Existing organisations without an OrganisationSubscription remain allowed so
    legacy/manual licences are not accidentally disabled by this enforcement pass.
    """
    current = _utc(now) or datetime.now(timezone.utc)
    if item is None:
        return SubscriptionAccess(
            status="unconfigured",
            allowed=True,
            warning=False,
            reason="legacy_manual",
            message="No subscription plan is configured; existing manual licence access remains available.",
        )

    status = str(item.status or "active").strip().lower()
    period_end = _utc(item.current_period_ends_at)
    trial_end = _utc(item.trial_ends_at)
    grace_end = _utc(item.grace_ends_at)

    if status == "trial":
        if trial_end and current >= trial_end:
            return SubscriptionAccess("expired", False, False, "trial_expired", "Your FAST trial has expired. Contact your administrator to continue using FAST applications.", trial_end)
        return SubscriptionAccess("trial", True, False, "trial", "FAST trial access is active.", trial_end)

    if status == "active":
        if item.cancel_at_period_end:
            if period_end and current >= period_end:
                return SubscriptionAccess("cancelled", False, False, "cancelled", "Your organisation's FAST subscription has ended. Contact your administrator to restore access.", period_end)
            return SubscriptionAccess("cancelled", True, True, "cancelling", "Your organisation's FAST subscription is cancelled and will remain available until the current paid period ends.", period_end)
        return SubscriptionAccess("active", True, False, "active", "FAST subscription is active.", period_end)

    if status in {"past_due", "grace_period"}:
        effective_end = grace_end or period_end
        if effective_end and current >= effective_end:
            return SubscriptionAccess("expired", False, False, "grace_expired", "Your organisation's FAST payment grace period has ended. Contact your administrator to restore access.", effective_end)
        return SubscriptionAccess(status, True, True, "payment_grace", "Your organisation's FAST subscription payment is past due. Access remains available during the grace period.", effective_end)

    if status == "cancelled":
        if period_end and current < period_end:
            return SubscriptionAccess("cancelled", True, True, "cancelled_pending", "Your organisation's FAST subscription is cancelled and remains available until the current paid period ends.", period_end)
        return SubscriptionAccess("cancelled", False, False, "cancelled", "Your organisation's FAST subscription has ended. Contact your administrator to restore access.", period_end)

    if status == "suspended":
        return SubscriptionAccess("suspended", False, False, "suspended", "Your organisation's FAST subscription has been suspended. Contact your administrator.")

    if status == "expired":
        return SubscriptionAccess("expired", False, False, "expired", "Your organisation's FAST subscription has expired. Contact your administrator to renew access.", period_end)

    return SubscriptionAccess(status, False, False, "unavailable", "Your organisation's FAST subscription is not currently available. Contact your administrator.")


def organisation_subscription_access(db: Session, organisation_id: int | None) -> SubscriptionAccess:
    if organisation_id is None:
        return SubscriptionAccess("not_applicable", True, False, "not_applicable", "Subscription enforcement does not apply to this account.")
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    access = evaluate_subscription(item)

    # Materialise time-based expiry so every caller sees the same authoritative
    # commercial state.  Stripe webhooks establish the grace deadline, but no
    # webhook is guaranteed to arrive at the exact instant that deadline passes.
    # The first authenticated FAST request after expiry therefore closes the
    # grace period server-side instead of leaving a stale ``grace_period`` row.
    if item is not None and access.reason in {"grace_expired", "trial_expired"}:
        stored_status = str(item.status or "").strip().lower()
        if stored_status != "expired":
            item.status = "expired"
            db.commit()

    return access
