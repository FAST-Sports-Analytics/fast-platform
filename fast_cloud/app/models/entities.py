from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserStatus(str, Enum):
    active = "active"
    suspended = "suspended"


class LicenceStatus(str, Enum):
    unused = "unused"
    active = "active"
    suspended = "suspended"
    revoked = "revoked"
    expired = "expired"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default=UserStatus.active.value)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    organisation_id: Mapped[int | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(40), default="analyst", index=True)
    verification_token: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    products_json: Mapped[str] = mapped_column(Text, default="[]")
    sports_json: Mapped[str] = mapped_column(Text, default="[]")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invitation_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    invitation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    licences: Mapped[list[Licence]] = relationship(back_populates="user", foreign_keys="Licence.user_id")
    club_memberships: Mapped[list[ClubMember]] = relationship(back_populates="user", cascade="all, delete-orphan")
    owned_clubs: Mapped[list[Club]] = relationship(back_populates="owner", foreign_keys="Club.owner_user_id")
    organisation: Mapped[Organisation | None] = relationship(foreign_keys=[organisation_id])


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscription_tier: Mapped[str] = mapped_column(String(80), default="FAST Professional")
    sports_json: Mapped[str] = mapped_column(Text, default="[]")
    max_seats: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    short_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    primary_colour: Mapped[str] = mapped_column(String(16), default="#19D978")
    secondary_colour: Mapped[str] = mapped_column(String(16), default="#151A1D")
    accent_colour: Mapped[str] = mapped_column(String(16), default="#19D978")
    status: Mapped[str] = mapped_column(String(30), default="active")
    deployment_ring: Mapped[str] = mapped_column(String(30), default="production", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    clubs: Mapped[list[Club]] = relationship(back_populates="organisation")


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    monthly_price_pence: Mapped[int] = mapped_column(Integer, default=0)
    annual_price_pence: Mapped[int] = mapped_column(Integer, default=0)
    trial_days: Mapped[int] = mapped_column(Integer, default=0)
    included_seats: Mapped[int] = mapped_column(Integer, default=1)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    products_json: Mapped[str] = mapped_column(Text, default="[]")
    sports_json: Mapped[str] = mapped_column(Text, default="[]")
    features_json: Mapped[str] = mapped_column(Text, default="{}")
    cloud_storage_gb: Mapped[int] = mapped_column(Integer, default=0)
    self_service_upgrades: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrganisationSubscription(Base):
    __tablename__ = "organisation_subscriptions"
    __table_args__ = (UniqueConstraint("organisation_id", name="uq_organisation_subscription"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("subscription_plans.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    billing_interval: Mapped[str] = mapped_column(String(20), default="monthly")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    seat_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    plan: Mapped[SubscriptionPlan | None] = relationship()
    organisation: Mapped[Organisation] = relationship()


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), default="stripe", index=True)
    external_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    organisation_id: Mapped[int | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    matched: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    processing_status: Mapped[str] = mapped_column(String(40), default="received", index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    organisation: Mapped[Organisation | None] = relationship()


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    organisation_id: Mapped[int | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User | None] = relationship(back_populates="owned_clubs", foreign_keys=[owner_user_id])
    organisation: Mapped[Organisation | None] = relationship(back_populates="clubs")
    members: Mapped[list[ClubMember]] = relationship(back_populates="club", cascade="all, delete-orphan")
    licences: Mapped[list[Licence]] = relationship(back_populates="club", foreign_keys="Licence.club_id")


class ClubMember(Base):
    __tablename__ = "club_members"
    __table_args__ = (UniqueConstraint("club_id", "user_id", name="uq_club_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(40), default="coach")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    club: Mapped[Club] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="club_memberships")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Sport(Base):
    __tablename__ = "sports"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LicenceTemplate(Base):
    __tablename__ = "licence_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    owner_type: Mapped[str] = mapped_column(String(20), default="individual")
    tier: Mapped[str] = mapped_column(String(80))
    products_json: Mapped[str] = mapped_column(Text, default="[]")
    sports_json: Mapped[str] = mapped_column(Text, default="[]")
    default_max_devices: Mapped[int] = mapped_column(Integer, default=1)
    default_max_users: Mapped[int] = mapped_column(Integer, default=1)
    default_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    renewable: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    licences: Mapped[list[Licence]] = relationship(back_populates="template")


class Licence(Base):
    __tablename__ = "licences"

    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code_last_four: Mapped[str] = mapped_column(String(4))
    tier: Mapped[str] = mapped_column(String(80))
    products_json: Mapped[str] = mapped_column(Text, default="[]")
    sports_json: Mapped[str] = mapped_column(Text, default="[]")
    features_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(30), default=LicenceStatus.unused.value)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    max_users: Mapped[int] = mapped_column(Integer, default=1)
    owner_type: Mapped[str] = mapped_column(String(20), default="individual")
    renewable: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("licence_templates.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User | None] = relationship(back_populates="licences", foreign_keys=[user_id])
    club: Mapped[Club | None] = relationship(back_populates="licences", foreign_keys=[club_id])
    template: Mapped[LicenceTemplate | None] = relationship(back_populates="licences")
    devices: Mapped[list[DeviceActivation]] = relationship(back_populates="licence", cascade="all, delete-orphan")


class DeviceActivation(Base):
    __tablename__ = "device_activations"
    __table_args__ = (UniqueConstraint("licence_id", "device_id", name="uq_licence_device"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    licence_id: Mapped[int] = mapped_column(ForeignKey("licences.id"))
    device_id: Mapped[str] = mapped_column(String(160), index=True)
    device_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    installed_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    update_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    update_health: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pending_update_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_telemetry_event: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deployment_ring: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    installed_products_json: Mapped[str] = mapped_column(Text, default="{}")
    product_health_json: Mapped[str] = mapped_column(Text, default="{}")
    live_status_json: Mapped[str] = mapped_column(Text, default="{}")

    licence: Mapped[Licence] = relationship(back_populates="devices")


class DeviceAuditLog(Base):
    __tablename__ = "device_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_activation_id: Mapped[int | None] = mapped_column(ForeignKey("device_activations.id"), nullable=True, index=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    target_label: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RemoteCommand(Base):
    __tablename__ = "remote_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_activation_id: Mapped[int] = mapped_column(ForeignKey("device_activations.id"), index=True)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    command: Mapped[str] = mapped_column(String(60), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



class CrashReport(Base):
    __tablename__ = "crash_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    component: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    exception_type: Mapped[str] = mapped_column(String(160), index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    organisation_id: Mapped[int | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    device_activation_id: Mapped[int | None] = mapped_column(ForeignKey("device_activations.id"), nullable=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    deployment_ring: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (UniqueConstraint("component", "version", "channel", name="uq_release_component_version_channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    component: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[str] = mapped_column(String(40), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="internal", index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_target: Mapped[str] = mapped_column(String(40), default="all", index=True)
    minimum_launcher_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    package_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    package_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    mandatory_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployment_ring: Mapped[str] = mapped_column(String(30), default="development", index=True)
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=100)
    rollout_status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    rollout_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
