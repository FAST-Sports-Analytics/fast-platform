from __future__ import annotations

import hashlib
import json
import logging
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
from app.core.data_retention import clear_organisation_deletion, schedule_organisation_deletion
from app.core.security import generate_licence_code, hash_licence_code, hash_password, normalise_licence_code
from app.db.session import SessionLocal, get_db
from app.models import AuditLog, BillingWebhookEvent, Club, ClubMember, DeviceActivation, Licence, Organisation, OrganisationSubscription, Sport, SubscriptionPlan, User

try:
    import stripe
except ImportError:  # Billing remains safely unavailable until dependency is installed.
    stripe = None

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
settings = get_settings()
logger = logging.getLogger("fast.billing")

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


def _billing_contact(db: Session, item: OrganisationSubscription | None) -> tuple[str, str]:
    if not item:
        return "", "your organisation"
    organisation = db.get(Organisation, item.organisation_id)
    if not organisation:
        return "", "your organisation"
    email = str(organisation.contact_email or "").strip().lower()
    if not email:
        admin = db.scalar(
            select(User).where(
                User.organisation_id == organisation.id,
                User.role == "administrator",
                User.status.in_(["active", "invited"]),
            ).order_by(User.id)
        )
        email = str(admin.email if admin else "").strip().lower()
    return email, organisation.name


def _send_billing_email(
    db: Session,
    item: OrganisationSubscription | None,
    *,
    subject: str,
    heading: str,
    intro: str,
    detail: str,
    action_label: str = "Manage FAST subscription",
) -> None:
    """Best-effort branded billing email; billing/webhooks must never fail because email did."""
    email, organisation_name = _billing_contact(db, item)
    if not email:
        return
    text_body, html_body = branded_action_email(
        heading=heading,
        intro=intro,
        action_label=action_label,
        action_url=f"{settings.public_app_url.rstrip('/')}/account",
        expiry_text=detail,
        footer_text=f"This message relates to the FAST subscription for {organisation_name}.",
    )
    try:
        send_email(to_email=email, subject=subject, text=text_body, html=html_body)
    except EmailDeliveryError:
        return


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
    subscription_metadata = _obj_get(subscription, "metadata", {}) or {}
    sport = _normalise_sport(
        str(
            _obj_get(session_metadata, "fast_sport", "")
            or _obj_get(subscription_metadata, "fast_sport", "")
            or ""
        )
    )
    raw_sports = str(
        _obj_get(session_metadata, "fast_sports", "")
        or _obj_get(subscription_metadata, "fast_sports", "")
        or ""
    )
    checkout_sports = [
        _normalise_sport(value)
        for value in raw_sports.split(",")
        if _normalise_sport(value) in SUPPORTED_SPORT_KEYS
    ]
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
    # Starter sells one sport. Professional sells up to five selected sports.
    # ``fast_sport`` remains as a backwards-compatible fallback for checkout
    # sessions created before multi-sport Professional selection was added.
    selected_sports = checkout_sports or ([sport] if sport else plan_sports)
    max_sports = 1 if str(plan.name or "").strip().lower() == "starter" else 5
    selected_sports = list(dict.fromkeys(selected_sports))[:max_sports]
    if not selected_sports:
        # A paid Starter/Professional organisation must never be materialised
        # without a sport entitlement. Leave the webhook retryable instead of
        # creating a broken "Sports: None" account.
        raise RuntimeError(
            f"Public FAST {plan.name} checkout is missing required sport metadata"
        )
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

    db.add(AuditLog(
        admin_user_id=admin_user.id,
        action="public_checkout_legal_acceptance",
        category="account_onboarding",
        target_type="organisation",
        target_id=organisation.id,
        target_label=organisation.name,
        details=(
            "Legal acceptance captured before Stripe checkout: "
            f"terms={str(_obj_get(session_metadata, 'fast_terms_version', '') or '')}; "
            f"dpa={str(_obj_get(session_metadata, 'fast_dpa_version', '') or '')}; "
            f"privacy_notice={str(_obj_get(session_metadata, 'fast_privacy_version', '') or '')}; "
            f"administrator_18_plus={str(_obj_get(session_metadata, 'fast_admin_18_plus', '') or '')}; "
            f"accepted_at={str(_obj_get(session_metadata, 'fast_legal_accepted_at', '') or '')}."
        ),
    ))

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


def _stripe_mode() -> str:
    key = _stripe_secret_key()
    if key.startswith("sk_live_"):
        return "live"
    if key.startswith("sk_test_"):
        return "test"
    return "unconfigured"


def _stripe_ready(*, webhook: bool = False) -> bool:
    if stripe is None or not _stripe_secret_key():
        return False
    return bool(_stripe_webhook_secret()) if webhook else True


def _configure_stripe() -> None:
    if stripe is not None:
        stripe.api_key = _stripe_secret_key()


def _checkout_tax_params(price) -> dict:
    """Return Stripe Checkout tax parameters without ever increasing FAST's advertised price accidentally.

    VAT is OFF by default. Once FAST is VAT registered, both VAT and Stripe
    automatic tax must be explicitly enabled and the selected Stripe Price must
    be tax-inclusive. If any of those safeguards are missing, checkout is
    blocked instead of silently adding tax on top of £39/£99/etc.
    """
    if not bool(settings.vat_enabled):
        return {}

    if not bool(settings.stripe_automatic_tax_enabled):
        raise HTTPException(
            status_code=503,
            detail="VAT billing is enabled but Stripe automatic tax is not enabled in FAST Cloud",
        )

    vat_number = str(settings.vat_registration_number or "").strip()
    if not vat_number:
        raise HTTPException(
            status_code=503,
            detail="VAT billing is enabled but the FAST VAT registration number is not configured",
        )

    tax_behavior = str(_obj_get(price, "tax_behavior", "") or "").strip().lower()
    if tax_behavior != "inclusive":
        raise HTTPException(
            status_code=503,
            detail=(
                "VAT billing requires an inclusive-tax Stripe Price so the advertised "
                "FAST price remains the final customer price"
            ),
        )

    return {
        "automatic_tax": {"enabled": True},
        "tax_id_collection": {"enabled": True},
    }


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


# Tier direction must be determined by FAST product level, not by the raw
# recurring price. For example Professional monthly -> Starter annual is still
# an entitlement downgrade even though £390/year is numerically greater than
# £99/month. Billing interval changes within the same tier are handled
# separately: annual -> monthly waits until period end; monthly -> annual is
# immediate and prorated by Stripe.
_FAST_PLAN_RANK: dict[str, int] = {
    "starter": 10,
    "professional": 20,
    "enterprise": 30,
    "custom": 40,
}


def _is_plan_downgrade(
    current_plan: SubscriptionPlan | None,
    target_plan: SubscriptionPlan,
    current_interval: str,
    target_interval: str,
) -> bool:
    if current_plan is None:
        return False

    if int(current_plan.id) == int(target_plan.id):
        return current_interval == "annual" and target_interval == "monthly"

    current_key = str(current_plan.name or "").strip().lower()
    target_key = str(target_plan.name or "").strip().lower()
    current_rank = _FAST_PLAN_RANK.get(current_key)
    target_rank = _FAST_PLAN_RANK.get(target_key)
    if current_rank is not None and target_rank is not None:
        return target_rank < current_rank

    # Defensive fallback for any future catalogue tier that has not yet been
    # assigned an explicit rank. Compare like-for-like monthly catalogue prices
    # rather than mixing monthly and annual totals.
    return int(target_plan.monthly_price_pence or 0) < int(current_plan.monthly_price_pence or 0)


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
            known_price_id = None
            if _stripe_mode() == "test":
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

            # Stripe Test Clocks advance Stripe's provider time without changing
            # Railway's wall clock. A schedule-managed cancellation can therefore
            # remain retrievable as an apparently active subscription while its
            # paid-through boundary is already in the past according to Stripe.
            # Reconcile that boundary explicitly even when retrieve() succeeds.
            provider_now = _stripe_test_clock_datetime(remote) or datetime.now(timezone.utc)
            period_end = item.current_period_ends_at
            if period_end and period_end.tzinfo is None:
                period_end = period_end.replace(tzinfo=timezone.utc)
            cancellation_due = bool(
                period_end
                and provider_now >= period_end
                and (
                    item.cancel_at_period_end
                    or _subscription_cancellation_scheduled(remote)
                    or _schedule_cancels_at_end(remote)
                )
            )
            if cancellation_due:
                item.status = "cancelled"
                item.cancel_at_period_end = False
                item.grace_ends_at = None
                organisation = db.get(Organisation, organisation_id)
                if organisation:
                    _revoke_subscription_entitlements(db, organisation, ended_at=period_end)
                    schedule_organisation_deletion(
                        db,
                        organisation,
                        reason="subscription_ended",
                        starts_at=period_end,
                        release_identity=False,
                    )
                item.updated_at = datetime.now(timezone.utc)

            # Payment-failure grace must use Stripe provider time as well. Test
            # Clocks can be weeks ahead of Railway's wall clock, so comparing
            # grace_ends_at only with datetime.now() leaves sandbox organisations
            # licensed indefinitely after their simulated grace period expires.
            grace_end = item.grace_ends_at
            if grace_end and grace_end.tzinfo is None:
                grace_end = grace_end.replace(tzinfo=timezone.utc)
            if item.status in {"grace_period", "past_due"} and grace_end and provider_now >= grace_end:
                # Grace expiry is a commercial cancellation, not merely a FAST
                # entitlement change. Terminate the Stripe contract as well so
                # Smart Retries stop and no future renewal is generated.
                _terminate_stripe_subscription_after_grace(item.external_subscription_id, remote)
                item.status = "cancelled"
                item.cancel_at_period_end = False
                item.grace_ends_at = None
                organisation = db.get(Organisation, organisation_id)
                if organisation:
                    _revoke_subscription_entitlements(db, organisation, ended_at=grace_end)
                    schedule_organisation_deletion(
                        db,
                        organisation,
                        reason="payment_grace_expired",
                        starts_at=grace_end,
                        release_identity=False,
                    )
                item.updated_at = datetime.now(timezone.utc)

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
            # A schedule-managed subscription can disappear from Stripe as soon
            # as its final paid phase ends.  If FAST already knows cancellation
            # was scheduled, use the customer's Stripe Test Clock during sandbox
            # simulations (or wall clock in live mode) to materialise terminal
            # expiry instead of leaving the last paid plan displayed forever.
            provider_now = _stripe_test_clock_datetime({"customer": item.external_customer_id}) or datetime.now(timezone.utc)
            period_end = item.current_period_ends_at
            if period_end and period_end.tzinfo is None:
                period_end = period_end.replace(tzinfo=timezone.utc)
            if item.cancel_at_period_end and period_end and provider_now >= period_end:
                item.status = "cancelled"
                item.cancel_at_period_end = False
                item.grace_ends_at = None
                organisation = db.get(Organisation, organisation_id)
                if organisation:
                    _revoke_subscription_entitlements(db, organisation, ended_at=period_end)
                    schedule_organisation_deletion(
                        db,
                        organisation,
                        reason="subscription_ended",
                        starts_at=period_end,
                        release_identity=False,
                    )
                item.updated_at = datetime.now(timezone.utc)
                db.commit()
            # Otherwise keep Organisation Management available if Stripe is
            # temporarily unreachable; the last successful state remains the
            # fallback and the normal webhook path can repair it later.
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

    next_payment_attempt_at = None
    overdue_amount_pence = None
    overdue_currency = None
    if status in {"grace_period", "past_due"} and billing_ready and item.external_subscription_id:
        try:
            _configure_stripe()
            remote_for_invoice = stripe.Subscription.retrieve(
                item.external_subscription_id,
                expand=["latest_invoice"],
            )
            latest_invoice = _obj_get(remote_for_invoice, "latest_invoice")
            if isinstance(latest_invoice, str) and latest_invoice:
                latest_invoice = stripe.Invoice.retrieve(latest_invoice)
            if latest_invoice:
                next_payment_attempt_at = _stripe_datetime(_obj_get(latest_invoice, "next_payment_attempt"))
                amount_remaining = _obj_get(latest_invoice, "amount_remaining")
                if amount_remaining is None:
                    amount_remaining = _obj_get(latest_invoice, "amount_due")
                if amount_remaining is not None:
                    overdue_amount_pence = int(amount_remaining)
                overdue_currency = str(_obj_get(latest_invoice, "currency", "") or "").upper() or None
        except Exception:
            # The grace deadline remains authoritative even if invoice display
            # metadata cannot be refreshed temporarily.
            pass

    # Stripe quantity scales plan capacity. ``seat_override`` stores the paid
    # user capacity after each Stripe sync; derive the matching device capacity
    # from the plan's base bundle so all API/UI checks use the same allowance.
    terminal_subscription = status in {"cancelled", "expired"} and not item.cancel_at_period_end
    effective_plan = None if terminal_subscription else plan_payload(item.plan)
    seat_limit = None
    device_limit = None
    if item.plan and not terminal_subscription:
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

    # Keep the customer subscription summary on the same authoritative device
    # inventory used by organisation management and capacity enforcement.
    active_devices = _organisation_active_device_count(db, organisation_id)

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
        "next_payment_attempt_at": next_payment_attempt_at.isoformat() if next_payment_attempt_at else None,
        "overdue_amount_pence": overdue_amount_pence,
        "overdue_currency": overdue_currency,
        "billing_provider": item.billing_provider,
        "seat_override": item.seat_override,
        "seat_limit": seat_limit,
        "seats_used": seats_used,
        "seat_over_limit": bool(seat_over_by),
        "seat_over_by": seat_over_by,
        "device_limit": device_limit,
        "active_devices": active_devices,
        "plan": effective_plan,
    }


def _organisation_active_device_count(db: Session, organisation_id: int) -> int:
    """Count active devices attached to any licence owned by this organisation."""
    club_device_ids = set(
        db.scalars(
            select(DeviceActivation.id)
            .join(Licence, Licence.id == DeviceActivation.licence_id)
            .join(Club, Club.id == Licence.club_id)
            .where(
                Club.organisation_id == organisation_id,
                DeviceActivation.active.is_(True),
            )
        ).all()
    )
    direct_device_ids = set(
        db.scalars(
            select(DeviceActivation.id)
            .join(Licence, Licence.id == DeviceActivation.licence_id)
            .join(User, User.id == Licence.user_id)
            .where(
                User.organisation_id == organisation_id,
                DeviceActivation.active.is_(True),
            )
        ).all()
    )
    return len(club_device_ids | direct_device_ids)


def _downgrade_capacity_payload(
    db: Session,
    organisation_id: int,
    target: SubscriptionPlan,
    item: OrganisationSubscription | None = None,
) -> dict:
    """Describe whether current organisation usage fits inside the target plan."""
    from app.core.seats import allocated_user_count

    seats_used = int(allocated_user_count(db, organisation_id))
    devices_used = int(_organisation_active_device_count(db, organisation_id))
    pending_user_ids: list[int] = []
    pending_device_ids: list[int] = []
    if item and item.pending_downgrade_plan_id == target.id:
        try:
            pending_user_ids = [int(value) for value in json.loads(item.pending_downgrade_user_ids_json or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            pending_user_ids = []
        try:
            pending_device_ids = [int(value) for value in json.loads(item.pending_downgrade_device_ids_json or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            pending_device_ids = []
    effective_seats_used = max(0, seats_used - len(set(pending_user_ids)))
    effective_devices_used = max(0, devices_used - len(set(pending_device_ids)))
    seat_limit = max(1, int(target.included_seats or 1))
    device_limit = max(1, int(target.max_devices or 1))

    blockers: list[str] = []
    if effective_seats_used > seat_limit:
        remove_count = effective_seats_used - seat_limit
        blockers.append(
            f"FAST {target.name} includes {seat_limit} licensed user"
            f"{'s' if seat_limit != 1 else ''}, but your organisation currently uses {seats_used}. "
            f"Remove or deactivate {remove_count} licensed user"
            f"{'s' if remove_count != 1 else ''} before continuing."
        )
    if effective_devices_used > device_limit:
        remove_count = effective_devices_used - device_limit
        blockers.append(
            f"FAST {target.name} allows {device_limit} active device"
            f"{'s' if device_limit != 1 else ''}, but your organisation currently uses {devices_used}. "
            f"Deactivate {remove_count} device"
            f"{'s' if remove_count != 1 else ''} before continuing."
        )

    return {
        "downgrade_blocked": bool(blockers),
        "downgrade_blockers": blockers,
        "current_seats_used": seats_used,
        "target_seat_limit": seat_limit,
        "current_devices_used": devices_used,
        "target_device_limit": device_limit,
        "pending_user_ids": pending_user_ids,
        "pending_device_ids": pending_device_ids,
    }


def _scheduled_plan_change_payload(db: Session, item: OrganisationSubscription) -> dict | None:
    """Return FAST's pending period-end subscription change, if any.

    A Stripe schedule can represent either a tier downgrade or a billing-interval
    change (for example Professional annual -> Professional monthly). Releasing
    the schedule cancels the future change while leaving the current paid
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

        current_plan = _plan_from_live_stripe_price(db, current_sub) or item.plan
        interval = str(metadata.get("fast_billing_interval") or item.billing_interval or "monthly").lower()
        if interval not in {"monthly", "annual"}:
            interval = "monthly"

        same_plan = bool(current_plan and int(current_plan.id) == int(target_plan.id))
        current_interval = str(item.billing_interval or "monthly").lower()
        if same_plan and interval == current_interval:
            # A future phase that repeats both the current tier and interval is
            # not a customer-visible subscription change.
            continue

        effective_at = _stripe_datetime(phase_start) or _stripe_datetime(current_phase_end)
        return {
            "type": "billing_interval" if same_plan else "downgrade",
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
        "billing_mode": _stripe_mode(),
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
    # ``sport`` is retained for backwards compatibility with older website builds.
    sport: str = Field(default="football", max_length=80)
    sports: list[str] = Field(default_factory=list, max_length=5)
    accept_terms: bool = False
    accept_dpa: bool = False
    confirm_admin_age: bool = False
    terms_version: str = Field(default="2026-08-20", max_length=40)
    dpa_version: str = Field(default="2026-08-20", max_length=40)
    privacy_version: str = Field(default="2026-08-20", max_length=40)


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
    if not payload.confirm_admin_age:
        raise HTTPException(status_code=422, detail="The organisation administrator must confirm they are at least 18")
    if not payload.accept_terms:
        raise HTTPException(status_code=422, detail="You must accept the FAST Terms of Service before checkout")
    if not payload.accept_dpa:
        raise HTTPException(status_code=422, detail="You must accept the FAST Data Processing Agreement before checkout")
    if payload.terms_version != "2026-08-20" or payload.dpa_version != "2026-08-20":
        raise HTTPException(status_code=409, detail="The FAST legal terms have changed. Refresh the page and review the current documents.")
    # Paid public checkout must carry an explicit sport selection from the
    # current website. Do not silently fall back to Football for an older/stale
    # frontend build: that can create a paid organisation with the wrong sports.
    requested_sports = [
        _normalise_sport(value)
        for value in payload.sports
        if _normalise_sport(value)
    ]
    requested_sports = list(dict.fromkeys(requested_sports))
    if not requested_sports:
        raise HTTPException(
            status_code=422,
            detail="Choose your licensed sport(s) before continuing to Stripe",
        )
    if any(value not in SUPPORTED_SPORT_KEYS for value in requested_sports):
        raise HTTPException(status_code=422, detail="Choose only supported FAST sports")

    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="That email already has a FAST account. Contact FAST to change an existing subscription.")
    if db.scalar(select(Organisation).where(func.lower(Organisation.name) == organisation_name.lower())):
        raise HTTPException(status_code=409, detail="That organisation already exists in FAST Cloud. Contact FAST to manage its subscription.")

    plan = db.get(SubscriptionPlan, payload.plan_id)
    if not plan or not plan.active:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    plan_key = str(plan.name or "").strip().lower()
    if plan_key not in {"starter", "professional"}:
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")
    max_sports = 1 if plan_key == "starter" else 5
    if len(requested_sports) > max_sports:
        raise HTTPException(
            status_code=422,
            detail=f"FAST {plan.name} includes up to {max_sports} sport{'s' if max_sports != 1 else ''}",
        )

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
        "fast_sport": requested_sports[0],
        "fast_sports": ",".join(requested_sports),
        "fast_terms_version": payload.terms_version,
        "fast_dpa_version": payload.dpa_version,
        "fast_privacy_version": payload.privacy_version,
        "fast_admin_18_plus": "1" if payload.confirm_admin_age else "0",
        "fast_legal_accepted_at": datetime.now(timezone.utc).isoformat(),
        "fast_vat_enabled": "1" if settings.vat_enabled else "0",
        "fast_price_policy": "customer_facing_price_is_final",
    }
    _configure_stripe()
    tax_params = _checkout_tax_params(price)
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
            **tax_params,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe Checkout could not be created: {exc}") from exc
    return {"url": _obj_get(session, "url"), "session_id": _obj_get(session, "id")}


class CheckoutRequest(BaseModel):
    plan_id: int
    billing_interval: str = "monthly"
    sports: list[str] = Field(default_factory=list, max_length=5)


def _validated_checkout_sports(payload: CheckoutRequest, plan: SubscriptionPlan) -> list[str]:
    plan_key = str(plan.name or "").strip().lower()
    if plan_key not in {"starter", "professional"}:
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")
    requested_sports = [
        _normalise_sport(value)
        for value in payload.sports
        if _normalise_sport(value)
    ]
    requested_sports = list(dict.fromkeys(requested_sports))
    if any(value not in SUPPORTED_SPORT_KEYS for value in requested_sports):
        raise HTTPException(status_code=422, detail="Choose only supported FAST sports")
    max_sports = 1 if plan_key == "starter" else 5
    if not requested_sports:
        raise HTTPException(status_code=422, detail="Choose your licensed sport(s) before continuing to Stripe")
    if len(requested_sports) > max_sports:
        raise HTTPException(
            status_code=422,
            detail=f"FAST {plan.name} includes up to {max_sports} sport{'s' if max_sports != 1 else ''}",
        )
    return requested_sports


@router.post("/checkout/preview")
def preview_checkout_capacity(
    payload: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Preview a new/resubscription checkout against retained organisation usage."""
    organisation_id = _require_org_admin(user)
    plan = db.get(SubscriptionPlan, payload.plan_id)
    if not plan or not plan.active:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    _validated_checkout_sports(payload, plan)
    interval = payload.billing_interval.lower().strip()
    if interval not in {"monthly", "annual"}:
        raise HTTPException(status_code=422, detail="Billing interval must be monthly or annual")
    item = db.scalar(
        select(OrganisationSubscription).where(
            OrganisationSubscription.organisation_id == organisation_id
        )
    )
    capacity = _downgrade_capacity_payload(db, organisation_id, plan, item)
    amount = plan.monthly_price_pence if interval == "monthly" else plan.annual_price_pence
    return {
        "change": "checkout",
        "effective": "now",
        "effective_at": None,
        "current_plan": None,
        "target_plan": plan_payload(plan),
        "current_billing_interval": None,
        "target_billing_interval": interval,
        "amount_due_now_pence": amount,
        "next_renewal_amount_pence": amount,
        "currency": "gbp",
        **capacity,
    }


@router.post("/checkout")
def create_checkout_session(payload: CheckoutRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")
    plan = db.get(SubscriptionPlan, payload.plan_id)
    if not plan or not plan.active:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    requested_sports = _validated_checkout_sports(payload, plan)
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

    capacity = _downgrade_capacity_payload(db, organisation_id, plan, current)
    if capacity["downgrade_blocked"]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "subscription_capacity_exceeded",
                "message": "Choose which licensed users/devices should be released before starting this subscription.",
                "capacity": capacity,
            },
        )

    price = _stripe_price_for_plan(plan, interval)
    customer_id = current.external_customer_id if current and current.external_customer_id else None
    customer_email = organisation.contact_email or user.email
    metadata = {
        "fast_organisation_id": str(organisation_id),
        "fast_plan_id": str(plan.id),
        "fast_billing_interval": interval,
        "fast_sport": requested_sports[0],
        "fast_sports": ",".join(requested_sports),
        "fast_vat_enabled": "1" if settings.vat_enabled else "0",
        "fast_price_policy": "customer_facing_price_is_final",
    }
    tax_params = _checkout_tax_params(price)
    params = {
        "mode": "subscription",
        "line_items": [{"price": str(_obj_get(price, "id")), "quantity": 1}],
        # Authenticated first-subscription checkout returns to the customer's
        # account page. Public /pricing checkout remains a separate onboarding
        # flow for organisations/users that do not exist yet.
        "success_url": f"{settings.public_app_url.rstrip('/')}/account?checkout=success",
        "cancel_url": f"{settings.public_app_url.rstrip('/')}/account?checkout=cancelled",
        "client_reference_id": str(organisation_id),
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        "allow_promotion_codes": True,
        **tax_params,
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
    sports: list[str] = Field(default_factory=list, max_length=5)


def _validated_plan_change_sports(
    payload: ChangePlanRequest,
    plan: SubscriptionPlan,
    *,
    require_selection: bool,
) -> list[str]:
    """Validate sport selection for an existing subscription plan change.

    A plan switch must explicitly carry the customer's target sports so an old
    Starter entitlement cannot silently survive a Professional upgrade. Billing
    interval-only changes may omit sports and preserve the existing metadata.
    """
    plan_key = str(plan.name or "").strip().lower()
    if plan_key not in {"starter", "professional"}:
        raise HTTPException(status_code=409, detail="This plan requires a FAST sales-assisted agreement")
    requested_sports = [
        _normalise_sport(value)
        for value in payload.sports
        if _normalise_sport(value)
    ]
    requested_sports = list(dict.fromkeys(requested_sports))
    if any(value not in SUPPORTED_SPORT_KEYS for value in requested_sports):
        raise HTTPException(status_code=422, detail="Choose only supported FAST sports")
    max_sports = 1 if plan_key == "starter" else 5
    if require_selection and not requested_sports:
        raise HTTPException(status_code=422, detail="Choose your licensed sport(s) before changing your FAST plan")
    if len(requested_sports) > max_sports:
        raise HTTPException(
            status_code=422,
            detail=f"FAST {plan.name} includes up to {max_sports} sport{'s' if max_sports != 1 else ''}",
        )
    return requested_sports


def _invoice_line_is_proration(line) -> bool:
    legacy = _obj_get(line, "proration")
    if legacy is not None:
        return bool(legacy)
    parent = _obj_get(line, "parent", {}) or {}
    details = _obj_get(parent, "subscription_item_details", {}) or {}
    return bool(_obj_get(details, "proration", False))


def _preview_plan_change_invoice(current_sub, subscription_item_id: str, target_price_id: str, quantity: int, proration_date: int | None = None):
    """Ask Stripe for a non-mutating preview of the proposed upgrade invoice.

    Stripe's Create Preview Invoice API is the source of truth for proration.
    When a Stripe Test Clock is attached, pass its frozen provider timestamp as
    the proration date. This keeps previews aligned with simulated Stripe time
    rather than Railway's wall clock. Live subscriptions can omit the value and
    let Stripe choose the effective timestamp.
    """
    params = {
        "subscription": str(_obj_get(current_sub, "id", "") or ""),
        "subscription_details": {
            "items": [{"id": subscription_item_id, "price": target_price_id, "quantity": quantity}],
            "proration_behavior": "always_invoice",
        },
    }
    if proration_date is not None:
        params["subscription_details"]["proration_date"] = int(proration_date)
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
    # Reconcile Stripe first so a newly failed renewal cannot slip through on a
    # stale local "active" state.
    subscription_payload(db, organisation_id, refresh_provider=True)
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if not item or item.billing_provider != "stripe" or not item.external_subscription_id:
        raise HTTPException(status_code=409, detail="This organisation does not have an active Stripe subscription")
    if str(item.status or "").lower() in {"past_due", "grace_period"}:
        raise HTTPException(
            status_code=409,
            detail="Payment required. Your FAST subscription has an overdue payment. Please settle the outstanding balance before changing your plan.",
        )
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
        plan_is_changing = not current_plan or current_plan.id != target.id
        requested_sports = _validated_plan_change_sports(payload, target, require_selection=plan_is_changing)
        if current_plan and current_plan.id == target.id and current_interval == interval:
            return {"change": "unchanged", "effective": "now", "target_plan": plan_payload(target)}

        target_amount = target.monthly_price_pence if interval == "monthly" else target.annual_price_pence
        is_downgrade = _is_plan_downgrade(current_plan, target, current_interval, interval)
        period_end = _subscription_period_end(current_sub)
        # Billing previews must follow Stripe provider time. Test Clock customers
        # can be months/years ahead of Railway's wall clock. Using wall time here
        # produced impossible renewal dates and incorrect annual-plan credits.
        preview_now = _stripe_test_clock_datetime(current_sub) or datetime.now(timezone.utc)
        provider_proration_date = int(preview_now.timestamp()) if _stripe_test_clock_datetime(current_sub) else None
        # Stripe resets the billing date when the recurring interval changes
        # (for example monthly -> annual). Reflect that new cycle in the
        # confirmation instead of showing the old monthly period end.
        next_renewal_at = period_end
        if not is_downgrade and current_interval != interval:
            next_renewal_at = _next_interval_renewal(preview_now, interval)
        common = {
            "change": "downgrade" if is_downgrade else "upgrade",
            "effective": "period_end" if is_downgrade else "now",
            "effective_at": period_end.isoformat() if is_downgrade and period_end else None,
            "current_plan": plan_payload(current_plan) if current_plan else None,
            "target_plan": plan_payload(target),
            "current_billing_interval": current_interval,
            "target_billing_interval": interval,
            "next_renewal_at": next_renewal_at.isoformat() if next_renewal_at else None,
            "next_renewal_amount_pence": target_amount,
            "currency": settings.billing_currency.lower(),
        }
        if is_downgrade:
            capacity = _downgrade_capacity_payload(db, organisation_id, target, item)
            return {
                **common,
                **capacity,
                "amount_due_now_pence": 0,
                "credit_pence": 0,
                "upgrade_charge_pence": 0,
                "proration_date": None,
            }

        quantity = max(1, int(_obj_get(first_item, "quantity", 1) or 1))
        preview = _preview_plan_change_invoice(
            current_sub,
            subscription_item_id,
            str(_obj_get(target_price, "id")),
            quantity,
            provider_proration_date,
        )
        lines = list(_obj_get(_obj_get(preview, "lines", {}), "data", []) or [])

        # TEMPORARY TEST 9 DIAGNOSTIC:
        # Log only billing/proration structure and amounts (no customer email,
        # payment method, card data or other sensitive fields). This lets us see
        # exactly what Stripe's Test Clock preview returns for Annual -> Monthly.
        diagnostic_lines = []
        for index, line in enumerate(lines):
            parent = _obj_get(line, "parent", {}) or {}
            subscription_details = _obj_get(parent, "subscription_item_details", {}) or {}
            period = _obj_get(line, "period", {}) or {}
            diagnostic_lines.append({
                "index": index,
                "amount": int(_obj_get(line, "amount", 0) or 0),
                "description": str(_obj_get(line, "description", "") or "")[:240],
                "legacy_proration": _obj_get(line, "proration"),
                "parent_type": _obj_get(parent, "type"),
                "parent_proration": _obj_get(subscription_details, "proration"),
                "period_start": _obj_get(period, "start"),
                "period_end": _obj_get(period, "end"),
            })
        logger.warning(
            "FAST_TEST9_STRIPE_PREVIEW %s",
            json.dumps({
                "current_interval": current_interval,
                "target_interval": interval,
                "provider_proration_date": provider_proration_date,
                "preview_amount_due": _obj_get(preview, "amount_due"),
                "preview_subtotal": _obj_get(preview, "subtotal"),
                "preview_total": _obj_get(preview, "total"),
                "line_count": len(lines),
                "lines": diagnostic_lines,
            }, default=str, separators=(",", ":")),
        )

        proration_lines = [line for line in lines if _invoice_line_is_proration(line)]

        # Stripe's newer preview-invoice line shape does not consistently expose
        # the legacy ``proration`` flag on both sides of an interval change.
        # In particular, the credit for unused annual time can be a negative
        # preview line whose parent metadata is shaped differently from the new
        # monthly charge.  Restricting the credit calculation to lines detected
        # by _invoice_line_is_proration therefore made a real annual credit show
        # as £0 in FAST even though Stripe had included it in the preview.
        #
        # A negative line in this non-mutating plan-change preview is a credit,
        # so include all negative preview lines.  Positive display charges still
        # prefer explicitly marked proration lines.  Stripe's amount_due remains
        # authoritative for the actual amount the customer would pay now.
        negative_lines = [
            line for line in lines
            if int(_obj_get(line, "amount", 0) or 0) < 0
        ]
        credit = sum(
            abs(int(_obj_get(line, "amount", 0) or 0))
            for line in negative_lines
        )

        positive_proration_lines = [
            line for line in proration_lines
            if int(_obj_get(line, "amount", 0) or 0) > 0
        ]
        if positive_proration_lines:
            charge = sum(
                int(_obj_get(line, "amount", 0) or 0)
                for line in positive_proration_lines
            )
        else:
            charge = sum(
                max(0, int(_obj_get(line, "amount", 0) or 0))
                for line in lines
            )

        preview_amount_due = _obj_get(preview, "amount_due")
        if preview_amount_due is not None:
            amount_due = max(0, int(preview_amount_due or 0))
        else:
            amount_due = max(0, charge - credit)
        return {
            **common,
            "amount_due_now_pence": amount_due,
            "credit_pence": credit,
            "upgrade_charge_pence": charge,
            # Kept in the response for backwards compatibility with the website,
            # but upgrades no longer send a host-clock proration timestamp back
            # to Stripe.
            "proration_date": None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe could not preview this plan change: {exc}") from exc


class DowngradeAccessSelectionRequest(BaseModel):
    plan_id: int
    user_ids: list[int] = Field(default_factory=list)
    device_ids: list[int] = Field(default_factory=list)


@router.post("/change-plan/stage-access")
def stage_downgrade_access(payload: DowngradeAccessSelectionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    organisation_id = _require_org_admin(user)
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    target = db.get(SubscriptionPlan, payload.plan_id)
    if not item or not target or not target.active:
        raise HTTPException(status_code=404, detail="FAST subscription or target plan was not found")
    raw_capacity = _downgrade_capacity_payload(db, organisation_id, target, None)
    users_required = max(0, int(raw_capacity["current_seats_used"]) - int(raw_capacity["target_seat_limit"]))
    devices_required = max(0, int(raw_capacity["current_devices_used"]) - int(raw_capacity["target_device_limit"]))
    user_ids = list(dict.fromkeys(int(value) for value in payload.user_ids))
    device_ids = list(dict.fromkeys(int(value) for value in payload.device_ids))
    if len(user_ids) != users_required or len(device_ids) != devices_required:
        raise HTTPException(status_code=409, detail="Select exactly the number of users and devices required for the destination plan")
    if user.id in user_ids:
        raise HTTPException(status_code=409, detail="Your own administrator account cannot be scheduled for suspension")
    if user_ids:
        valid_users = set(db.scalars(select(User.id).where(User.organisation_id == organisation_id, User.id.in_(user_ids), User.status.in_(["active", "invited"]))).all())
        if valid_users != set(user_ids):
            raise HTTPException(status_code=409, detail="One or more selected users are not active members of this organisation")
    if device_ids:
        valid_devices = set(db.scalars(select(DeviceActivation.id).join(Licence, Licence.id == DeviceActivation.licence_id).outerjoin(Club, Club.id == Licence.club_id).outerjoin(User, User.id == Licence.user_id).where(DeviceActivation.id.in_(device_ids), DeviceActivation.active.is_(True), ((Club.organisation_id == organisation_id) | (User.organisation_id == organisation_id)))).all())
        if valid_devices != set(device_ids):
            raise HTTPException(status_code=409, detail="One or more selected devices are not active devices for this organisation")
    item.pending_downgrade_plan_id = target.id
    item.pending_downgrade_user_ids_json = json.dumps(user_ids)
    item.pending_downgrade_device_ids_json = json.dumps(device_ids)
    terminal_checkout = str(item.status or "").lower() in {"cancelled", "expired"}
    item.pending_downgrade_effective_at = None if terminal_checkout else item.current_period_ends_at
    db.add(AuditLog(
        admin_user_id=user.id,
        action="subscription_checkout_access_staged" if terminal_checkout else "subscription_downgrade_access_staged",
        category="billing",
        target_type="organisation",
        target_id=organisation_id,
        target_label=str(organisation_id),
        details=(
            f"Selected {len(user_ids)} user licence release(s) and {len(device_ids)} device deactivation(s) for new FAST {target.name} subscription activation."
            if terminal_checkout
            else f"Scheduled {len(user_ids)} user suspension(s) and {len(device_ids)} device deactivation(s) for FAST {target.name} downgrade."
        ),
    ))
    db.commit()
    return {"staged": True, "effective_at": item.pending_downgrade_effective_at.isoformat() if item.pending_downgrade_effective_at else None, "capacity": _downgrade_capacity_payload(db, organisation_id, target, item)}


@router.post("/change-plan")
def change_subscription_plan(payload: ChangePlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Change an existing Stripe subscription without creating a second subscription.

    Upgrades are applied immediately and Stripe prorates the remaining period.
    Downgrades are scheduled for the next renewal so paid access is retained.
    """
    organisation_id = _require_org_admin(user)
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")
    # Reconcile Stripe first so a newly failed renewal cannot slip through on a
    # stale local "active" state.
    subscription_payload(db, organisation_id, refresh_provider=True)
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if not item or item.billing_provider != "stripe" or not item.external_subscription_id:
        raise HTTPException(status_code=409, detail="This organisation does not have an active Stripe subscription")
    if str(item.status or "").lower() in {"past_due", "grace_period"}:
        raise HTTPException(
            status_code=409,
            detail="Payment required. Your FAST subscription has an overdue payment. Please settle the outstanding balance before changing your plan.",
        )
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
        current_interval = _subscription_billing_interval(current_sub, item.billing_interval)
        plan_is_changing = not current_plan or current_plan.id != target.id
        requested_sports = _validated_plan_change_sports(payload, target, require_selection=plan_is_changing)
        if current_plan and current_plan.id == target.id and current_interval == interval:
            return {"change": "unchanged", "effective": "now", "subscription": subscription_payload(db, organisation_id)}

        target_amount = target.monthly_price_pence if interval == "monthly" else target.annual_price_pence
        is_downgrade = _is_plan_downgrade(current_plan, target, current_interval, interval)
        metadata = dict(_obj_get(current_sub, "metadata", {}) or {})
        metadata.update({"fast_organisation_id": str(organisation_id), "fast_plan_id": str(target.id), "fast_billing_interval": interval})
        if requested_sports:
            metadata.update({
                "fast_sport": requested_sports[0],
                "fast_sports": ",".join(requested_sports),
            })

        if is_downgrade:
            capacity = _downgrade_capacity_payload(db, organisation_id, target, item)
            if capacity["downgrade_blocked"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": f"Your organisation does not currently fit within FAST {target.name} limits.",
                        **capacity,
                    },
                )

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

            # The live subscription period end is the authoritative boundary
            # for a newly requested FAST period-end change. An existing Stripe
            # schedule can have a much later current_phase.end_date left over
            # from an earlier scheduled interval/plan change. Reusing that stale
            # phase end postpones the new change (for example, Apr 2028 became
            # Feb 2029). Shorten/rebuild the current schedule phase to the live
            # subscription's current paid-period end instead.
            phase_end_ts = int(period_end.timestamp())
            current_phase_start_ts = int(current_phase_start)
            if phase_end_ts <= current_phase_start_ts:
                raise HTTPException(
                    status_code=409,
                    detail="Stripe returned an invalid billing period boundary for the scheduled plan change",
                )
            item.pending_downgrade_effective_at = period_end
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
                        # FAST period-end plan/interval changes begin a new paid
                        # billing cycle at the phase boundary.  This is essential
                        # for Stripe subscriptions using flexible billing mode:
                        # flexible mode deliberately preserves the old billing
                        # cycle anchor unless we explicitly reset it.  Without
                        # phase_start, a Monthly -> Annual downgrade can enter
                        # the annual phase without charging the annual price
                        # until the following year.
                        "billing_cycle_anchor": "phase_start",
                        "proration_behavior": "none",
                    },
                ],
            )
            db.add(AuditLog(admin_user_id=user.id, action="subscription_downgrade_scheduled", category="billing", target_type="organisation", target_id=organisation_id, target_label=str(organisation_id), details=f"Scheduled {target.name} ({interval}) for next renewal."))
            db.commit()
            _send_billing_email(
                db, item,
                subject=f"FAST {target.name} change scheduled",
                heading="FAST plan change scheduled",
                intro=f"Your organisation is scheduled to move to FAST {target.name} ({interval}) at the end of the current paid period.",
                detail=f"The change is scheduled for {period_end.strftime('%d %B %Y')}. Your current paid access remains unchanged until then.",
                action_label="Review plan change",
            )
            return {"change": "downgrade", "effective": "period_end", "effective_at": period_end.isoformat(), "target_plan": plan_payload(target), "subscription": subscription_payload(db, organisation_id)}

        update_params = {
            "items": [{"id": subscription_item_id, "price": str(_obj_get(target_price, "id")), "quantity": max(1, int(_obj_get(sub_items[0], "quantity", 1) or 1))}],
            "metadata": metadata,
            # Upgrades are charged immediately. Stripe credits the unused part
            # of the old plan and invoices only the net proration now.
            "proration_behavior": "always_invoice",
        }
        provider_now = _stripe_test_clock_datetime(current_sub)
        if provider_now is not None:
            update_params["proration_date"] = int(provider_now.timestamp())
        # Let Stripe choose the effective proration timestamp. In test-clock
        # subscriptions the simulated Stripe time can differ substantially from
        # datetime.now() on Railway; forwarding the preview/client timestamp can
        # therefore be outside the active subscription phase and Stripe rejects
        # the upgrade.
        updated = stripe.Subscription.modify(item.external_subscription_id, **update_params)

        # Stripe can leave upgrade prorations as pending invoice items even
        # when the subscription update uses always_invoice. If that happens,
        # explicitly invoice those pending items now so the customer pays only
        # the net upgrade proration immediately and the next renewal remains a
        # normal full-plan invoice.
        customer_id = str(_obj_get(_obj_get(updated, "customer"), "id", _obj_get(updated, "customer", "")) or "").strip()
        if customer_id:
            pending = stripe.InvoiceItem.list(
                customer=customer_id,
                pending=True,
                limit=100,
            )
            pending_items = list(_obj_get(pending, "data", []) or [])
            upgrade_pending = [
                invoice_item
                for invoice_item in pending_items
                if str(_obj_get(_obj_get(invoice_item, "subscription"), "id", _obj_get(invoice_item, "subscription", "")) or "").strip()
                == item.external_subscription_id
            ]
            if upgrade_pending:
                invoice = stripe.Invoice.create(
                    customer=customer_id,
                    subscription=item.external_subscription_id,
                    auto_advance=True,
                    description=f"FAST {target.name} upgrade proration",
                )
                invoice_id = str(_obj_get(invoice, "id", "") or "").strip()
                if invoice_id:
                    invoice = stripe.Invoice.finalize_invoice(invoice_id)
                    status = str(_obj_get(invoice, "status", "") or "").lower()
                    amount_due = int(_obj_get(invoice, "amount_due", 0) or 0)
                    if amount_due > 0 and status not in {"paid", "void", "uncollectible"}:
                        stripe.Invoice.pay(invoice_id)

        refreshed = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        _sync_stripe_subscription(db, refreshed, organisation_id_override=organisation_id)
        db.add(AuditLog(admin_user_id=user.id, action="subscription_upgraded", category="billing", target_type="organisation", target_id=organisation_id, target_label=str(organisation_id), details=f"Changed to {target.name} ({interval})."))
        db.commit()
        _send_billing_email(
            db, item,
            subject=f"Your FAST subscription is now {target.name}",
            heading=f"FAST {target.name} is active",
            intro=f"Your organisation has successfully changed to FAST {target.name} ({interval}).",
            detail="The new plan and its licensed-user, device and product allowances are now active. Stripe has applied any billing adjustment for the change.",
        )
        return {"change": "upgrade", "effective": "now", "target_plan": plan_payload(target), "subscription": subscription_payload(db, organisation_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe subscription could not be changed: {exc}") from exc


@router.post("/change-plan/cancel-scheduled")
def cancel_scheduled_plan_change(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Cancel a pending FAST period-end subscription change.

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
            raise HTTPException(status_code=409, detail="There is no scheduled FAST subscription change to cancel")

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
        item.pending_downgrade_plan_id = None
        item.pending_downgrade_user_ids_json = "[]"
        item.pending_downgrade_device_ids_json = "[]"
        item.pending_downgrade_effective_at = None
        db.add(
            AuditLog(
                admin_user_id=user.id,
                action="subscription_scheduled_change_cancelled",
                category="billing",
                target_type="organisation",
                target_id=organisation_id,
                target_label=str(organisation_id),
                details="Scheduled subscription change cancelled; current plan and billing interval retained.",
            )
        )
        db.commit()
        return {
            "cancelled": True,
            "message": "Scheduled billing change cancelled. Your current FAST subscription will continue unchanged.",
            "subscription": subscription_payload(db, organisation_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe scheduled subscription change could not be cancelled: {exc}") from exc


@router.post("/cancel")
def cancel_subscription_at_period_end(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Schedule the organisation's Stripe subscription to end after paid access expires."""
    organisation_id = _require_org_admin(user)
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if not item or item.billing_provider != "stripe" or not item.external_subscription_id:
        raise HTTPException(status_code=409, detail="This organisation does not have an active Stripe subscription")
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")
    if item.status not in {"active", "trial"}:
        raise HTTPException(status_code=409, detail="Only an active FAST subscription can be cancelled")

    _configure_stripe()
    try:
        current_sub = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        if _scheduled_plan_change_payload(db, item):
            raise HTTPException(status_code=409, detail="Cancel the scheduled plan or billing change before cancelling your FAST subscription")
        if _subscription_cancellation_scheduled(current_sub):
            _sync_stripe_subscription(db, current_sub, organisation_id_override=organisation_id)
            db.commit()
            return {"cancelled_at_period_end": True, "message": "Your FAST subscription is already scheduled to cancel at the end of the paid period.", "subscription": subscription_payload(db, organisation_id)}

        schedule_id = _subscription_schedule_id(current_sub)
        if schedule_id:
            # Stripe forbids changing cancellation fields directly while a
            # Subscription Schedule owns the subscription.  Make the schedule
            # cancel when its current/final phase ends instead.  This also
            # covers subscriptions that reached a downgraded phase but remain
            # schedule-managed until that phase completes.
            stripe.SubscriptionSchedule.modify(schedule_id, end_behavior="cancel")
            updated = None
        else:
            updated = stripe.Subscription.modify(item.external_subscription_id, cancel_at_period_end=True)
        refreshed = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        _sync_stripe_subscription(db, refreshed or updated, organisation_id_override=organisation_id)
        if schedule_id and not item.cancel_at_period_end:
            # Some Stripe API versions do not mirror schedule end_behavior onto
            # cancel_at/cancel_at_period_end immediately. Persist the equivalent
            # FAST state so the website accurately shows the pending expiry.
            item.cancel_at_period_end = True
        db.add(AuditLog(admin_user_id=user.id, action="subscription_cancellation_scheduled", category="billing", target_type="organisation", target_id=organisation_id, target_label=str(organisation_id), details="Subscription cancellation scheduled for the end of the current paid period."))
        db.commit()
        _send_billing_email(
            db, item,
            subject="Your FAST subscription is scheduled to end",
            heading="FAST cancellation scheduled",
            intro="Your FAST subscription has been scheduled to cancel at the end of the current paid period.",
            detail=f"Your FAST access remains available until {item.current_period_ends_at.strftime('%d %B %Y') if item.current_period_ends_at else 'the end of the current paid period'}. You can keep the subscription from your FAST account before it ends.",
            action_label="Review subscription",
        )
        return {"cancelled_at_period_end": True, "message": "Cancellation scheduled. Your FAST access will continue until the end of your current paid period.", "subscription": subscription_payload(db, organisation_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe subscription cancellation could not be scheduled: {exc}") from exc


@router.post("/cancel/undo")
def undo_subscription_cancellation(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Remove a pending period-end cancellation and keep the current subscription active."""
    organisation_id = _require_org_admin(user)
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation_id))
    if not item or item.billing_provider != "stripe" or not item.external_subscription_id:
        raise HTTPException(status_code=409, detail="This organisation does not have an active Stripe subscription")
    if not _stripe_ready():
        raise HTTPException(status_code=503, detail="Online billing is not configured yet")

    _configure_stripe()
    try:
        current_sub = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        if not (_subscription_cancellation_scheduled(current_sub) or _schedule_cancels_at_end(current_sub)):
            _sync_stripe_subscription(db, current_sub, organisation_id_override=organisation_id)
            db.commit()
            return {"cancellation_removed": True, "message": "Your FAST subscription is already set to continue.", "subscription": subscription_payload(db, organisation_id)}

        schedule_id = _subscription_schedule_id(current_sub)
        schedule_cancellation = _schedule_cancels_at_end(current_sub) if schedule_id else False
        if schedule_cancellation:
            # Restore the schedule's normal release behaviour so the current
            # subscription continues after the scheduled phase.
            stripe.SubscriptionSchedule.modify(schedule_id, end_behavior="release")
            updated = None
        else:
            updated = stripe.Subscription.modify(item.external_subscription_id, cancel_at_period_end=False)
        refreshed = stripe.Subscription.retrieve(item.external_subscription_id, expand=["items.data.price"])
        _sync_stripe_subscription(db, refreshed or updated, organisation_id_override=organisation_id)
        if schedule_cancellation:
            item.cancel_at_period_end = False
        db.add(AuditLog(admin_user_id=user.id, action="subscription_cancellation_reversed", category="billing", target_type="organisation", target_id=organisation_id, target_label=str(organisation_id), details="Scheduled subscription cancellation removed; current subscription will renew normally."))
        db.commit()
        _send_billing_email(
            db, item,
            subject="Your FAST subscription will continue",
            heading="FAST cancellation removed",
            intro="The scheduled cancellation has been removed and your FAST subscription will continue.",
            detail=f"Your subscription will renew normally on {item.current_period_ends_at.strftime('%d %B %Y') if item.current_period_ends_at else 'its next renewal date'}.",
        )
        return {"cancellation_removed": True, "message": "Cancellation removed. Your FAST subscription will continue and renew normally.", "subscription": subscription_payload(db, organisation_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe subscription cancellation could not be reversed: {exc}") from exc


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


def _apply_payment_failure(
    db: Session,
    invoice,
    *,
    occurred_at: datetime | None = None,
) -> OrganisationSubscription | None:
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
            _sync_stripe_subscription(db, remote, grace_reference_at=occurred_at)
        except Exception:
            # The invoice failure itself is still authoritative enough to place
            # an already-matched FAST subscription into grace.
            pass

    item.status = "grace_period"
    now = datetime.now(timezone.utc)
    grace_reference = occurred_at or now
    grace_candidate = grace_reference + timedelta(days=max(1, settings.billing_grace_days))
    # The grace deadline belongs to the original failed renewal, not to each
    # subsequent Stripe Smart Retry.  Once grace has started, preserve that
    # deadline so repeated payment failures cannot extend FAST access.
    if not item.grace_ends_at:
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


def _stripe_test_clock_datetime(value) -> datetime | None:
    """Return Stripe Test Clock frozen time when this object belongs to one.

    Stripe webhook ``event.created`` uses real wall-clock time even when the
    customer/subscription is being advanced by a sandbox Test Clock.  Billing
    lifecycle deadlines must therefore use the clock's ``frozen_time`` during
    simulations, while live Stripe objects naturally fall back to event time.
    """
    if not _stripe_ready():
        return None

    test_clock_id = str(_obj_get(value, "test_clock", "") or "").strip()
    customer_id = _stripe_customer_id(value)

    if not test_clock_id and customer_id:
        try:
            _configure_stripe()
            customer = stripe.Customer.retrieve(customer_id)
            test_clock_id = str(_obj_get(customer, "test_clock", "") or "").strip()
        except Exception:
            test_clock_id = ""

    if not test_clock_id:
        return None

    try:
        _configure_stripe()
        test_clock = stripe.test_helpers.TestClock.retrieve(test_clock_id)
        return _stripe_datetime(_obj_get(test_clock, "frozen_time"))
    except Exception:
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


def _next_interval_renewal(anchor: datetime, interval: str) -> datetime:
    """Return the next full renewal after an immediate billing-interval switch."""
    if interval == "annual":
        try:
            return anchor.replace(year=anchor.year + 1)
        except ValueError:
            # 29 February -> 28 February in a non-leap renewal year.
            return anchor.replace(year=anchor.year + 1, day=28)
    if interval == "monthly":
        year = anchor.year + (1 if anchor.month == 12 else 0)
        month = 1 if anchor.month == 12 else anchor.month + 1
        # Clamp end-of-month anchors where the target month is shorter.
        day = anchor.day
        while day > 28:
            try:
                return anchor.replace(year=year, month=month, day=day)
            except ValueError:
                day -= 1
        return anchor.replace(year=year, month=month, day=day)
    return anchor


def _subscription_cancel_at(subscription) -> datetime | None:
    """Return Stripe's explicit scheduled cancellation timestamp, if present.

    Stripe Billing Portal can represent an end-of-period cancellation with an
    explicit ``cancel_at`` timestamp even when ``cancel_at_period_end`` is false.
    FAST normalises either representation into its existing cancellation flag.
    """
    return _stripe_datetime(_obj_get(subscription, "cancel_at"))


def _subscription_cancellation_scheduled(subscription) -> bool:
    return bool(_obj_get(subscription, "cancel_at_period_end", False) or _subscription_cancel_at(subscription))


def _subscription_schedule_id(subscription) -> str:
    schedule_ref = _obj_get(subscription, "schedule")
    return str(_obj_get(schedule_ref, "id", schedule_ref) or "").strip()


def _schedule_cancels_at_end(subscription) -> bool:
    """Return whether an attached Stripe Subscription Schedule ends by cancelling."""
    schedule_id = _subscription_schedule_id(subscription)
    if not schedule_id:
        return False
    schedule = stripe.SubscriptionSchedule.retrieve(schedule_id)
    return (
        str(_obj_get(schedule, "status", "") or "").lower() in {"active", "not_started"}
        and str(_obj_get(schedule, "end_behavior", "") or "").lower() == "cancel"
    )


def _terminate_stripe_subscription_after_grace(subscription_id: str, subscription=None) -> None:
    """Terminate Stripe billing when FAST's payment-failure grace period expires.

    Schedule-managed subscriptions must be cancelled through the Subscription
    Schedule API; Stripe rejects direct subscription cancellation mutations while
    the schedule owns the subscription. Any still-open invoices for the ended
    contract are voided so Stripe Smart Retries cannot continue after FAST has
    cancelled access.
    """
    if not subscription_id or not _stripe_ready():
        return

    _configure_stripe()
    current = subscription or stripe.Subscription.retrieve(subscription_id)
    schedule_id = _subscription_schedule_id(current)

    if schedule_id:
        schedule = stripe.SubscriptionSchedule.retrieve(schedule_id)
        schedule_status = str(_obj_get(schedule, "status", "") or "").lower()
        if schedule_status in {"active", "not_started"}:
            stripe.SubscriptionSchedule.cancel(schedule_id)
    else:
        status = str(_obj_get(current, "status", "") or "").lower()
        if status not in {"canceled", "cancelled", "incomplete_expired"}:
            stripe.Subscription.cancel(subscription_id)

    # Cancellation does not necessarily erase an already-open renewal invoice.
    # FAST's grace policy treats the debt as closed once access is terminated,
    # therefore void open invoices to stop any further automatic collection.
    invoices = stripe.Invoice.list(subscription=subscription_id, status="open", limit=100)
    for invoice in _obj_get(invoices, "data", []) or []:
        invoice_id = str(_obj_get(invoice, "id", "") or "").strip()
        if invoice_id:
            stripe.Invoice.void_invoice(invoice_id)



def _revoke_subscription_entitlements(
    db: Session, organisation: Organisation, *, ended_at: datetime | None = None
) -> None:
    """Revoke licence-backed FAST access after a commercial subscription ends.

    The subscription row is retained for billing history/resubscription, but all
    organisation-owned desktop licences are made non-current so Launcher cannot
    continue using paid applications after the final paid period.
    """
    effective_end = ended_at or datetime.now(timezone.utc)
    organisation.expires_at = effective_end
    organisation.max_seats = 0

    club_ids = list(
        db.scalars(
            select(Club.id).where(Club.organisation_id == organisation.id)
        ).all()
    )
    if club_ids:
        licences = db.scalars(
            select(Licence).where(
                Licence.club_id.in_(club_ids),
                Licence.owner_type == "club",
            )
        ).all()
        for licence in licences:
            licence.status = "expired"
            licence.renewable = False
            licence.expires_at = effective_end
    db.flush()

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
    grace_reference_at: datetime | None = None,
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
    previous_plan_id = item.plan_id
    previous_external_subscription_id = str(item.external_subscription_id or "")
    previous_status = str(item.status or "").lower()
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
            grace_reference = grace_reference_at or datetime.now(timezone.utc)
            item.grace_ends_at = grace_reference + timedelta(days=max(1, settings.billing_grace_days))
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
    if item.status in {"active", "trial", "grace_period", "past_due"} and organisation.deletion_scheduled_at:
        clear_organisation_deletion(db, organisation)

    if effective_plan:
        organisation.subscription_tier = effective_plan.name
        # Stripe quantity is the paid capacity multiplier. Store the resulting
        # user-seat allowance as the subscription override because the shared
        # seat evaluator otherwise falls back to the plan's single-unit limit.
        item.seat_override = max(1, int(effective_plan.included_seats or 1)) * quantity
        organisation.max_seats = item.seat_override
        organisation.expires_at = item.current_period_ends_at
        # Only commercially live states may provision an active desktop licence.
        # Stripe can still include the old price/plan on a terminal cancelled
        # object; re-provisioning it here would incorrectly restore paid access.
        if item.status in {"active", "trial", "grace_period", "past_due"}:
            metadata_sports = [
                _normalise_sport(value)
                for value in str(_obj_get(metadata, "fast_sports", "") or "").split(",")
                if _normalise_sport(value) in SUPPORTED_SPORT_KEYS
            ]
            metadata_sports = list(dict.fromkeys(metadata_sports))
            max_sports = 1 if str(effective_plan.name or "").strip().lower() == "starter" else 5
            if metadata_sports:
                organisation.sports_json = json.dumps(metadata_sports[:max_sports])
            _ensure_subscription_entitlements(db, organisation, effective_plan, quantity=quantity)
        else:
            _revoke_subscription_entitlements(
                db, organisation, ended_at=item.current_period_ends_at or datetime.now(timezone.utc)
            )
        # Apply any access reductions chosen when a period-end downgrade was
        # scheduled. Paid access remains unchanged until Stripe switches plans.
        current_external_subscription_id = str(_obj_get(subscription, "id", "") or "")
        is_new_subscription = bool(
            current_external_subscription_id
            and current_external_subscription_id != previous_external_subscription_id
        )
        terminal_resubscription = previous_status in {"cancelled", "expired"} and is_new_subscription
        plan_switched = previous_plan_id != effective_plan.id
        if item.pending_downgrade_plan_id == effective_plan.id and (plan_switched or terminal_resubscription):
            try:
                pending_user_ids = [int(value) for value in json.loads(item.pending_downgrade_user_ids_json or "[]")]
            except (TypeError, ValueError, json.JSONDecodeError):
                pending_user_ids = []
            try:
                pending_device_ids = [int(value) for value in json.loads(item.pending_downgrade_device_ids_json or "[]")]
            except (TypeError, ValueError, json.JSONDecodeError):
                pending_device_ids = []
            if pending_user_ids:
                for pending_user in db.scalars(select(User).where(User.organisation_id == organisation.id, User.id.in_(pending_user_ids))).all():
                    pending_user.status = "suspended"
            if pending_device_ids:
                for pending_device in db.scalars(select(DeviceActivation).where(DeviceActivation.id.in_(pending_device_ids))).all():
                    pending_device.active = False
            item.pending_downgrade_plan_id = None
            item.pending_downgrade_user_ids_json = "[]"
            item.pending_downgrade_device_ids_json = "[]"
            item.pending_downgrade_effective_at = None
        for club in organisation.clubs:
            for licence in club.licences:
                if licence.status == "active":
                    licence.expires_at = item.current_period_ends_at



def _record_subscription_billing_audit(
    db: Session,
    item: OrganisationSubscription | None,
    *,
    action: str,
    details: str,
    external_event_id: str = "",
) -> None:
    """Write one organisation billing audit record for a matched Stripe event.

    BillingWebhookEvent remains the low-level provider diagnostic log. AuditLog
    is the human-facing customer/organisation history shown in FAST Cloud Admin.
    Stripe can retry the same webhook, so use the provider event id in details
    and suppress duplicate AuditLog rows for that event.
    """
    if not item:
        return

    organisation = db.get(Organisation, item.organisation_id)
    if not organisation:
        return

    admin_user = db.scalar(
        select(User).where(
            User.organisation_id == organisation.id,
            User.role == "administrator",
            User.status.in_(["active", "invited"]),
        ).order_by(User.id)
    )
    if not admin_user:
        return

    event_marker = f"stripe_event={external_event_id}" if external_event_id else ""
    if event_marker:
        duplicate = db.scalar(
            select(AuditLog.id).where(
                AuditLog.category == "billing",
                AuditLog.target_type == "organisation",
                AuditLog.target_id == organisation.id,
                AuditLog.details.contains(event_marker),
            )
        )
        if duplicate:
            return

    audit_details = details.strip()
    if event_marker:
        audit_details = f"{audit_details} {event_marker}".strip()

    db.add(
        AuditLog(
            admin_user_id=admin_user.id,
            action=action,
            category="billing",
            target_type="organisation",
            target_id=organisation.id,
            target_label=organisation.name,
            details=audit_details,
        )
    )


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
    external_event_id = str(_obj_get(event, "id", "") or "")
    event_created_at = _stripe_datetime(_obj_get(event, "created"))
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
                    if matched_item:
                        plan = db.get(SubscriptionPlan, matched_item.plan_id) if matched_item.plan_id else None
                        organisation = db.get(Organisation, matched_item.organisation_id)
                        selected_sports = _loads(organisation.sports_json, []) if organisation else []
                        _record_subscription_billing_audit(
                            db,
                            matched_item,
                            action="subscription_started",
                            details=(
                                f"Stripe checkout completed; FAST {plan.name if plan else 'subscription'} "
                                f"({matched_item.billing_interval}) activated"
                                f"; sports={', '.join(selected_sports) if selected_sports else 'none'}"
                                f"; status={matched_item.status}."
                            ),
                            external_event_id=external_event_id,
                        )
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
                # A subscription.updated event can be the first Stripe event that
                # moves a failed Test Clock subscription to past_due. If we seed
                # grace from the webhook event timestamp here, the later invoice
                # failure correctly preserves that deadline -- but it preserves a
                # real wall-clock deadline instead of simulated time. Resolve the
                # Test Clock for subscription lifecycle events too, so whichever
                # event establishes grace first uses the same simulated reference.
                subscription_occurred_at = _stripe_test_clock_datetime(sync_source) or event_created_at
                _sync_stripe_subscription(db, sync_source, grace_reference_at=subscription_occurred_at)
                matched_item = _subscription_for_stripe_reference(
                    db,
                    subscription_id=referenced_subscription_id,
                    customer_id=_stripe_customer_id(sync_source),
                )
                if matched_item:
                    if event_type == "customer.subscription.deleted":
                        # A deleted Stripe subscription is terminal: the paid period has
                        # already ended (or the subscription was cancelled immediately).
                        # Preserve the last known paid-through timestamp for account
                        # history, but revoke every licence-backed entitlement now.
                        terminal_end = matched_item.current_period_ends_at or subscription_occurred_at or event_created_at or datetime.now(timezone.utc)
                        matched_item.status = "cancelled"
                        matched_item.cancel_at_period_end = False
                        matched_item.grace_ends_at = None
                        matched_item.updated_at = datetime.now(timezone.utc)
                        terminal_org = db.get(Organisation, matched_item.organisation_id)
                        if terminal_org:
                            _revoke_subscription_entitlements(db, terminal_org, ended_at=terminal_end)
                            schedule_organisation_deletion(
                                db,
                                terminal_org,
                                reason="subscription_ended",
                                starts_at=terminal_end,
                                release_identity=False,
                            )
                        details = "Stripe subscription deleted; FAST paid access and licence entitlements revoked. Customer data scheduled for deletion after the 31-day recovery period."
                        _record_subscription_billing_audit(
                            db,
                            matched_item,
                            action="subscription_ended",
                            details=details,
                            external_event_id=external_event_id,
                        )
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
                # Test Clock webhook events retain their real delivery timestamp.
                # Use the simulated clock's frozen time for grace deadlines when
                # available; live customers have no test_clock and use event time.
                failure_occurred_at = _stripe_test_clock_datetime(data) or event_created_at
                matched_item = _apply_payment_failure(db, data, occurred_at=failure_occurred_at)
                if matched_item:
                    details = (
                        f"Payment failure applied; FAST access remains available during grace until "
                        f"{matched_item.grace_ends_at.isoformat() if matched_item.grace_ends_at else 'not set'}."
                    )
                    _record_subscription_billing_audit(
                        db,
                        matched_item,
                        action="payment_failed",
                        details=details,
                        external_event_id=external_event_id,
                    )
                    _send_billing_email(
                        db, matched_item,
                        subject="Action required: FAST payment failed",
                        heading="We couldn't collect your FAST payment",
                        intro="Stripe could not collect the latest payment for your FAST subscription.",
                        detail=f"FAST access remains available during the payment grace period until {matched_item.grace_ends_at.strftime('%d %B %Y') if matched_item.grace_ends_at else 'the grace period ends'}. Update your payment method to avoid losing access.",
                        action_label="Fix payment",
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
                    _record_subscription_billing_audit(
                        db,
                        matched_item,
                        action="payment_received",
                        details=details,
                        external_event_id=external_event_id,
                    )
                    _send_billing_email(
                        db, matched_item,
                        subject="FAST payment received",
                        heading="Your FAST payment was successful",
                        intro="The outstanding payment has been received and your FAST subscription is active.",
                        detail="Any payment grace state has been cleared. Your organisation can continue using its licensed FAST products normally.",
                    )
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
