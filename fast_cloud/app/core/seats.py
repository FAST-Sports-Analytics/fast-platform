from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Club, ClubMember, Licence, Organisation, OrganisationSubscription, User
from app.core.access_grants import current_access_grant

ALLOCATED_USER_STATUSES = {"active", "invited"}
USABLE_LICENCE_STATUSES = {"unused", "active"}


def _licence_current(licence: Licence) -> bool:
    if str(licence.status or "").lower() not in USABLE_LICENCE_STATUSES:
        return False
    expires_at = licence.expires_at
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


def effective_user_seat_limit(db: Session, organisation: Organisation) -> int:
    grant = current_access_grant(db, organisation.id)
    if grant is not None:
        return max(1, int(grant.max_users or 1))
    subscription = db.scalar(
        select(OrganisationSubscription).where(
            OrganisationSubscription.organisation_id == organisation.id
        )
    )
    if subscription:
        if subscription.seat_override:
            return max(1, int(subscription.seat_override))
        if subscription.plan and subscription.plan.included_seats:
            return max(1, int(subscription.plan.included_seats))
    return max(1, int(organisation.max_seats or 1))


def allocated_user_ids(db: Session, organisation_id: int) -> set[int]:
    direct_ids = set(
        db.scalars(
            select(User.id).where(
                User.organisation_id == organisation_id,
                User.status.in_(sorted(ALLOCATED_USER_STATUSES)),
            )
        ).all()
    )
    club_ids = set(
        db.scalars(
            select(ClubMember.user_id)
            .join(Club, Club.id == ClubMember.club_id)
            .join(User, User.id == ClubMember.user_id)
            .where(
                Club.organisation_id == organisation_id,
                User.status.in_(sorted(ALLOCATED_USER_STATUSES)),
            )
        ).all()
    )
    return direct_ids | club_ids


def allocated_user_count(db: Session, organisation_id: int) -> int:
    return len(allocated_user_ids(db, organisation_id))


def user_would_consume_new_seat(db: Session, organisation_id: int, user_id: int) -> bool:
    return user_id not in allocated_user_ids(db, organisation_id)


def club_user_limit(club: Club) -> int | None:
    limits = [
        int(licence.max_users or 0)
        for licence in club.licences
        if _licence_current(licence) and int(licence.max_users or 0) > 0
    ]
    return max(limits) if limits else None


def club_allocated_user_count(club: Club) -> int:
    return len({
        membership.user_id
        for membership in club.members
        if str(membership.user.status or "").lower() in ALLOCATED_USER_STATUSES
    })


def organisation_device_capacity(organisation: Organisation) -> int:
    return sum(
        int(licence.max_devices or 0)
        for club in organisation.clubs
        for licence in club.licences
        if _licence_current(licence)
    )
