from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    if current and current <= scheduled_at:
        scheduled_at = current
    else:
        organisation.deletion_requested_at = requested_at
        organisation.deletion_scheduled_at = scheduled_at
        organisation.deletion_reason = str(reason or "customer_deletion")[:80]

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


def purge_due_organisations(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Purge all customer organisations whose 31-day recovery period has expired."""
    current = _utc(now) or datetime.now(timezone.utc)
    due = db.scalars(
        select(Organisation)
        .where(
            Organisation.deletion_scheduled_at.is_not(None),
            Organisation.deletion_scheduled_at <= current,
        )
        .order_by(Organisation.deletion_scheduled_at)
    ).all()

    purged = 0
    for organisation in due:
        label = organisation.name
        scheduled_at = _utc(organisation.deletion_scheduled_at)
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
