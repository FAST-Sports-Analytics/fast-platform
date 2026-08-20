from __future__ import annotations

from datetime import datetime, timedelta, timezone

import stripe

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import EmailDeliveryError, branded_action_email, send_email

from app.models import (
    AuditLog,
    BillingWebhookEvent,
    Club,
    ClubMember,
    CrashReport,
    DeviceActivation,
    DeviceAuditLog,
    Licence,
    Organisation,
    OrganisationSubscription,
    Release,
    RemoteCommand,
    User,
)

RETENTION_DAYS = 31
settings = get_settings()


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _platform_admin(db: Session) -> User | None:
    return db.scalar(
        select(User)
        .where(User.is_admin.is_(True), User.organisation_id.is_(None))
        .order_by(User.id)
        .limit(1)
    )


def _retention_audit(
    db: Session,
    organisation: Organisation,
    *,
    action: str,
    details: str,
) -> None:
    admin = _platform_admin(db)
    if not admin:
        return
    db.add(
        AuditLog(
            admin_user_id=admin.id,
            action=action,
            category="data_retention",
            target_type="organisation",
            target_id=organisation.id,
            target_label=organisation.name,
            details=details,
        )
    )



def _retention_contact(db: Session, organisation: Organisation) -> tuple[str, str]:
    email = str(organisation.contact_email or "").strip().lower()
    admin = db.scalar(
        select(User).where(
            User.organisation_id == organisation.id,
            User.role == "administrator",
            User.status.in_(["active", "invited", "suspended"]),
        ).order_by(User.id)
    )
    if not email and admin:
        email = str(admin.retention_email or admin.email or "").strip().lower()
    name = str((admin.full_name if admin else "") or organisation.contact_name or organisation.retention_name or organisation.name or "FAST customer").strip()
    return email, name


def _send_retention_notice(
    db: Session,
    organisation: Organisation,
    *,
    reason: str,
    purge_at: datetime,
) -> None:
    """Best-effort customer notice when FAST starts a 31-day recovery period."""
    email, contact_name = _retention_contact(db, organisation)
    if not email:
        return

    clean_reason = str(reason or "").strip().lower()
    purge_label = purge_at.astimezone(timezone.utc).strftime("%d %B %Y at %H:%M UTC")

    if clean_reason in {"subscription_ended", "payment_grace_expired"}:
        subject = "Your FAST subscription has ended"
        heading = "Your FAST subscription has ended"
        intro = (
            f"Hello {contact_name}. Your organisation's paid FAST subscription has ended "
            "and licensed FAST product access has been removed."
        )
        detail = (
            f"Your organisation's operational data is now in FAST's 31-day recovery period "
            f"and is scheduled for permanent deletion on {purge_label}. "
            "If you reactivate before that date, the scheduled deletion will be cancelled."
        )
        action_label = "View FAST account"
    else:
        subject = "FAST account deletion scheduled"
        heading = "Your FAST account deletion is scheduled"
        intro = (
            f"Hello {contact_name}. FAST has received the request to delete your customer account."
        )
        detail = (
            f"Your retained operational customer data is scheduled for permanent deletion on "
            f"{purge_label}, after the 31-day recovery period."
        )
        action_label = "FAST Sports Analytics"

    text_body, html_body = branded_action_email(
        heading=heading,
        intro=intro,
        action_label=action_label,
        action_url=f"{settings.public_app_url.rstrip('/')}/account",
        expiry_text=detail,
        footer_text=(
            "This is an automated FAST data-retention notice. "
            "For assistance contact support@fastsportsanalytics.com."
        ),
    )
    try:
        send_email(to_email=email, subject=subject, text=text_body, html=html_body)
        _retention_audit(
            db,
            organisation,
            action="deletion_notice_sent",
            details=f"31-day retention notice sent to {email}; purge_at={purge_at.isoformat()}.",
        )
    except EmailDeliveryError as exc:
        _retention_audit(
            db,
            organisation,
            action="deletion_notice_failed",
            details=(
                f"31-day retention notice could not be delivered to {email}; "
                f"purge_at={purge_at.isoformat()}; error={str(exc)[:240]}."
            ),
        )

def schedule_organisation_deletion(
    db: Session,
    organisation: Organisation,
    *,
    reason: str,
    starts_at: datetime | None = None,
    release_identity: bool = False,
) -> datetime:
    """Schedule customer operational data for purge after the 31-day recovery period.

    ``release_identity`` is used for an explicit account/customer deletion. The
    old customer is made inaccessible immediately and email addresses are moved
    to retention-only fields, allowing the same email to create a genuinely new
    FAST customer without reconnecting to the retained organisation.
    """
    requested_at = _utc(starts_at) or datetime.now(timezone.utc)
    scheduled_at = requested_at + timedelta(days=RETENTION_DAYS)

    # Never shorten an already-running retention period accidentally.
    current = _utc(organisation.deletion_scheduled_at)
    newly_scheduled = not bool(current)
    if current and current <= scheduled_at:
        scheduled_at = current
    else:
        organisation.deletion_requested_at = requested_at
        organisation.deletion_scheduled_at = scheduled_at
        organisation.deletion_reason = str(reason or "customer_deletion")[:80]
        newly_scheduled = True

    # Capture/send the notice before an explicit account deletion releases the
    # customer's public email identity.
    if newly_scheduled:
        _send_retention_notice(
            db,
            organisation,
            reason=reason,
            purge_at=scheduled_at,
        )

    if release_identity:
        organisation.status = "pending_deletion"
        stamp = int(requested_at.timestamp())
        if not organisation.retention_name:
            organisation.retention_name = organisation.name
        organisation.name = f"deleted-{organisation.id}-{stamp}"
        if organisation.contact_email:
            organisation.contact_email = None

        users = db.scalars(
            select(User).where(User.organisation_id == organisation.id)
        ).all()
        for user in users:
            if not user.retention_email:
                user.retention_email = user.email
            # Free the unique public email address while retaining the account
            # internally for the recovery period.
            user.email = f"deleted+{user.id}+{stamp}@retention.invalid"
            user.status = "pending_deletion"
            user.products_json = "[]"
            user.sports_json = "[]"
            user.verification_token = None
            user.invitation_token_hash = None
            user.invitation_expires_at = None
            user.password_reset_token_hash = None
            user.password_reset_expires_at = None

    # Scheduling can be reached more than once from Stripe lifecycle sync/webhooks.
    # Only create a new audit row when the retention deadline was actually created
    # or changed; otherwise repeated provider events make the audit trail noisy.
    if newly_scheduled:
        _retention_audit(
            db,
            organisation,
            action="deletion_scheduled",
            details=(
                f"31-day customer data recovery period scheduled; reason={reason}; "
                f"purge_at={scheduled_at.isoformat()}; identity_released={bool(release_identity)}."
            ),
        )
    return scheduled_at


def clear_organisation_deletion(
    db: Session,
    organisation: Organisation,
    *,
    restore_identity: bool = False,
) -> bool:
    """Cancel a scheduled purge, normally because the customer re-subscribed."""
    if not organisation.deletion_scheduled_at:
        return False

    if restore_identity and organisation.status == "pending_deletion":
        # Do not create duplicate identities if the customer has already used
        # the released email/name to create a new FAST account.
        original_name = (organisation.retention_name or "").strip()
        if original_name:
            name_collision = db.scalar(
                select(Organisation.id).where(
                    Organisation.name == original_name,
                    Organisation.id != organisation.id,
                )
            )
            if name_collision:
                return False

        users = db.scalars(
            select(User).where(User.organisation_id == organisation.id)
        ).all()
        for user in users:
            original = (user.retention_email or "").strip().lower()
            if not original:
                continue
            collision = db.scalar(
                select(User.id).where(
                    User.email == original,
                    User.id != user.id,
                )
            )
            if collision:
                return False

    old_due = _utc(organisation.deletion_scheduled_at)
    organisation.deletion_requested_at = None
    organisation.deletion_scheduled_at = None
    organisation.deletion_reason = None

    if restore_identity and organisation.status == "pending_deletion":
        if organisation.retention_name:
            organisation.name = organisation.retention_name
            organisation.retention_name = None

        users = db.scalars(
            select(User).where(User.organisation_id == organisation.id)
        ).all()
        for user in users:
            original = (user.retention_email or "").strip().lower()
            if original:
                user.email = original
                user.retention_email = None
            user.status = "active"
        organisation.status = "active"

    _retention_audit(
        db,
        organisation,
        action="deletion_cancelled",
        details=(
            "Scheduled customer data deletion cancelled"
            + (f"; previous_purge_at={old_due.isoformat()}" if old_due else "")
            + "."
        ),
    )
    return True


def hard_delete_customer_organisation(db: Session, organisation: Organisation) -> None:
    """Permanently purge an organisation after its recovery period has expired."""
    subscription = db.scalar(
        select(OrganisationSubscription).where(
            OrganisationSubscription.organisation_id == organisation.id
        )
    )

    # Keep non-customer-specific provider/crash diagnostics usable without an FK
    # to the deleted organisation. Their own retention schedule is separate.
    db.query(BillingWebhookEvent).filter(
        BillingWebhookEvent.organisation_id == organisation.id
    ).update(
        {
            BillingWebhookEvent.organisation_id: None,
            BillingWebhookEvent.matched: False,
        },
        synchronize_session=False,
    )
    db.query(CrashReport).filter(
        CrashReport.organisation_id == organisation.id
    ).update(
        {CrashReport.organisation_id: None},
        synchronize_session=False,
    )
    if subscription:
        db.delete(subscription)

    clubs = db.scalars(
        select(Club).where(Club.organisation_id == organisation.id)
    ).all()
    for club in clubs:
        licence_ids = [
            item.id
            for item in db.scalars(
                select(Licence).where(Licence.club_id == club.id)
            ).all()
        ]
        if licence_ids:
            device_ids = [
                item.id
                for item in db.scalars(
                    select(DeviceActivation).where(
                        DeviceActivation.licence_id.in_(licence_ids)
                    )
                ).all()
            ]
            if device_ids:
                db.query(RemoteCommand).filter(
                    RemoteCommand.device_activation_id.in_(device_ids)
                ).delete(synchronize_session=False)
                db.query(DeviceAuditLog).filter(
                    DeviceAuditLog.device_activation_id.in_(device_ids)
                ).delete(synchronize_session=False)
            db.query(DeviceActivation).filter(
                DeviceActivation.licence_id.in_(licence_ids)
            ).delete(synchronize_session=False)
            db.query(Licence).filter(
                Licence.id.in_(licence_ids)
            ).delete(synchronize_session=False)

        db.query(ClubMember).filter(
            ClubMember.club_id == club.id
        ).delete(synchronize_session=False)
        db.delete(club)

    users = db.scalars(
        select(User).where(User.organisation_id == organisation.id)
    ).all()
    for user in users:
        user_licence_ids = [
            item.id
            for item in db.scalars(
                select(Licence).where(Licence.user_id == user.id)
            ).all()
        ]
        if user_licence_ids:
            device_ids = [
                item.id
                for item in db.scalars(
                    select(DeviceActivation).where(
                        DeviceActivation.licence_id.in_(user_licence_ids)
                    )
                ).all()
            ]
            if device_ids:
                db.query(RemoteCommand).filter(
                    RemoteCommand.device_activation_id.in_(device_ids)
                ).delete(synchronize_session=False)
                db.query(DeviceAuditLog).filter(
                    DeviceAuditLog.device_activation_id.in_(device_ids)
                ).delete(synchronize_session=False)
            db.query(DeviceActivation).filter(
                DeviceActivation.licence_id.in_(user_licence_ids)
            ).delete(synchronize_session=False)
            db.query(Licence).filter(
                Licence.id.in_(user_licence_ids)
            ).delete(synchronize_session=False)

        db.query(ClubMember).filter(ClubMember.user_id == user.id).delete(synchronize_session=False)
        db.query(Club).filter(Club.owner_user_id == user.id).update(
            {Club.owner_user_id: None}, synchronize_session=False
        )
        db.query(CrashReport).filter(CrashReport.user_id == user.id).update(
            {CrashReport.user_id: None}, synchronize_session=False
        )
        db.query(Release).filter(Release.created_by_user_id == user.id).update(
            {Release.created_by_user_id: None}, synchronize_session=False
        )
        db.query(RemoteCommand).filter(
            RemoteCommand.requested_by_user_id == user.id
        ).delete(synchronize_session=False)
        db.query(DeviceAuditLog).filter(
            DeviceAuditLog.admin_user_id == user.id
        ).delete(synchronize_session=False)
        # Customer-authored audit rows cannot outlive their FK user row. Platform
        # retention audit rows use the platform administrator and remain.
        db.query(AuditLog).filter(
            AuditLog.admin_user_id == user.id
        ).delete(synchronize_session=False)
        db.delete(user)

    db.delete(organisation)


def _stripe_object_id(value) -> str:
    """Return a Stripe resource ID from either an ID string or expanded object."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("id") or "").strip()
    return str(getattr(value, "id", "") or "").strip()


def _stripe_test_clock_details_for_organisation(
    db: Session, organisation: Organisation
) -> tuple[datetime | None, str]:
    """Return sandbox Test Clock time + id for an organisation when available.

    A cancelled Stripe subscription can stop exposing ``test_clock`` through the
    Customer object even though its invoices were created on that Test Clock.
    For retention testing we therefore resolve the clock in this order:

    1. Stored/retrievable Subscription object.
    2. Customer object.
    3. Latest invoice for the Stripe customer.

    Live Stripe customers do not have a Test Clock, so all three naturally
    return no clock and FAST falls back to real UTC time.
    """
    if not settings.stripe_secret_key:
        return None, ""

    subscription = db.scalar(
        select(OrganisationSubscription).where(
            OrganisationSubscription.organisation_id == organisation.id
        )
    )
    if not subscription:
        return None, ""

    customer_id = str(subscription.external_customer_id or "").strip()
    subscription_id = str(subscription.external_subscription_id or "").strip()
    if not customer_id and not subscription_id:
        return None, ""

    try:
        stripe.api_key = settings.stripe_secret_key
        test_clock_id = ""

        # A live/cancelled subscription may still be retrievable and is the most
        # direct source when Stripe keeps the object available.
        if subscription_id:
            try:
                remote_subscription = stripe.Subscription.retrieve(subscription_id)
                test_clock_id = _stripe_object_id(
                    getattr(remote_subscription, "test_clock", None)
                )
                if not test_clock_id and isinstance(remote_subscription, dict):
                    test_clock_id = _stripe_object_id(
                        remote_subscription.get("test_clock")
                    )
            except Exception:
                test_clock_id = ""

        # Customer is normally enough while the Test Clock relationship remains
        # exposed by Stripe.
        if not test_clock_id and customer_id:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                test_clock_id = _stripe_object_id(
                    getattr(customer, "test_clock", None)
                )
                if not test_clock_id and isinstance(customer, dict):
                    test_clock_id = _stripe_object_id(customer.get("test_clock"))
            except Exception:
                test_clock_id = ""

        # Important cancellation fallback: invoices created under a Test Clock
        # retain their ``test_clock`` reference even after the subscription has
        # reached its terminal state. This lets the 31-day purge test continue
        # to use Stripe's simulated time after cancellation.
        if not test_clock_id and customer_id:
            try:
                invoices = stripe.Invoice.list(customer=customer_id, limit=10)
                invoice_rows = list(getattr(invoices, "data", None) or [])
                if not invoice_rows and isinstance(invoices, dict):
                    invoice_rows = list(invoices.get("data") or [])
                for invoice in invoice_rows:
                    test_clock_id = _stripe_object_id(
                        getattr(invoice, "test_clock", None)
                    )
                    if not test_clock_id and isinstance(invoice, dict):
                        test_clock_id = _stripe_object_id(invoice.get("test_clock"))
                    if test_clock_id:
                        break
            except Exception:
                test_clock_id = ""

        if not test_clock_id:
            return None, ""

        test_clock = stripe.test_helpers.TestClock.retrieve(test_clock_id)
        frozen_time = getattr(test_clock, "frozen_time", None)
        if frozen_time is None and isinstance(test_clock, dict):
            frozen_time = test_clock.get("frozen_time")
        if not frozen_time:
            return None, test_clock_id

        return (
            datetime.fromtimestamp(int(frozen_time), tz=timezone.utc),
            test_clock_id,
        )
    except Exception:
        # Retention must remain available if Stripe is temporarily unreachable.
        # The next hourly pass retries automatically.
        return None, ""


def _stripe_test_clock_now_for_organisation(
    db: Session, organisation: Organisation
) -> datetime | None:
    provider_now, _clock_id = _stripe_test_clock_details_for_organisation(
        db, organisation
    )
    return provider_now



def retention_diagnostics(db: Session) -> list[dict]:
    """Return read-only retention timing diagnostics for administrator tooling."""
    wall_clock_now = datetime.now(timezone.utc)
    organisations = db.scalars(
        select(Organisation)
        .where(Organisation.deletion_scheduled_at.is_not(None))
        .order_by(Organisation.deletion_scheduled_at)
    ).all()
    rows: list[dict] = []
    for organisation in organisations:
        scheduled_at = _utc(organisation.deletion_scheduled_at)
        provider_now, test_clock_id = _stripe_test_clock_details_for_organisation(
            db, organisation
        )
        effective_now = provider_now or wall_clock_now
        subscription = db.scalar(
            select(OrganisationSubscription).where(
                OrganisationSubscription.organisation_id == organisation.id
            )
        )
        rows.append({
            "organisation_id": organisation.id,
            "organisation": organisation.retention_name or organisation.name,
            "deletion_scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "real_utc_now": wall_clock_now.isoformat(),
            "effective_now": effective_now.isoformat(),
            "using_stripe_test_clock": provider_now is not None,
            "stripe_test_clock_id": test_clock_id or None,
            "stripe_customer_id": (subscription.external_customer_id if subscription else None),
            "is_due": bool(scheduled_at and scheduled_at <= effective_now),
        })
    return rows

def purge_due_organisations(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Purge all customer organisations whose 31-day recovery period has expired."""
    wall_clock_now = _utc(now) or datetime.now(timezone.utc)
    candidates = db.scalars(
        select(Organisation)
        .where(Organisation.deletion_scheduled_at.is_not(None))
        .order_by(Organisation.deletion_scheduled_at)
    ).all()

    purged = 0
    for organisation in candidates:
        scheduled_at = _utc(organisation.deletion_scheduled_at)
        if not scheduled_at:
            continue

        # An explicit ``now`` is authoritative for tests/callers. Otherwise use
        # Stripe's Test Clock for sandbox customers and real UTC for live ones.
        current = wall_clock_now
        if now is None:
            provider_now = _stripe_test_clock_now_for_organisation(db, organisation)
            if provider_now is not None:
                current = provider_now
        if scheduled_at > current:
            continue

        label = organisation.name
        _retention_audit(
            db,
            organisation,
            action="deletion_purged",
            details=(
                f"31-day recovery period expired; permanent customer operational "
                f"data purge initiated at {current.isoformat()}; "
                f"scheduled_at={scheduled_at.isoformat() if scheduled_at else 'unknown'}."
            ),
        )
        # Flush the platform audit row before deleting customer users.
        db.flush()
        hard_delete_customer_organisation(db, organisation)
        purged += 1

    if purged:
        db.commit()
    return purged
