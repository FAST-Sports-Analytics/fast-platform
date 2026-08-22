from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.access_grants import current_access_grant, grant_payload
from app.core.security import generate_licence_code, hash_licence_code, normalise_licence_code
from app.db.session import get_db
from app.models import AuditLog, BetaAccessCode, BetaCodeRedemption, Club, ClubMember, Licence, Organisation, OrganisationAccessGrant, User

router = APIRouter(tags=["Access Programmes"])
BETA_TERMS_VERSION = "2026-08-22"


def _dump(items) -> str:
    return json.dumps(sorted(set(str(x).strip().lower() for x in items if str(x).strip())))


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def _new_beta_code() -> str:
    return "FAST-BETA-" + secrets.token_hex(4).upper()


class GrantRequest(BaseModel):
    tier: str = "FAST Professional"
    products: list[str] = Field(default_factory=lambda: ["analysis", "viewer"])
    sports: list[str] = Field(default_factory=lambda: ["football"])
    features: dict | list = Field(default_factory=dict)
    max_devices: int = Field(5, ge=1, le=1000)
    max_users: int = Field(5, ge=1, le=1000)
    release_channel: str = "stable"
    expires_at: datetime | None = None
    reason: str | None = None


class BetaCodeRequest(BaseModel):
    label: str | None = None
    tier: str = "FAST Beta"
    products: list[str] = Field(default_factory=lambda: ["analysis", "viewer"])
    sports: list[str] = Field(default_factory=lambda: ["football"])
    features: dict | list = Field(default_factory=dict)
    max_devices: int = Field(2, ge=1, le=1000)
    max_users: int = Field(2, ge=1, le=1000)
    release_channel: str = "beta"
    duration_days: int = Field(60, ge=1, le=730)
    max_redemptions: int = Field(1, ge=1, le=10000)
    expires_at: datetime | None = None


class RedeemRequest(BaseModel):
    code: str
    organisation_name: str | None = None
    accept_beta_terms: bool = False
    beta_terms_version: str = BETA_TERMS_VERSION


def _platform_admin(user: User) -> None:
    if not bool(user.is_admin and user.organisation_id is None):
        raise HTTPException(status_code=403, detail="FAST platform administrator access required")


def _ensure_org_runtime(db: Session, user: User, organisation: Organisation, *, tier: str, products_json: str, sports_json: str, features_json: str, max_devices: int, max_users: int) -> Licence:
    club = db.scalar(select(Club).where(Club.organisation_id == organisation.id).order_by(Club.id))
    if club is None:
        base = organisation.name.strip() or f"Organisation {organisation.id}"
        name = base
        suffix = 2
        while db.scalar(select(Club.id).where(func.lower(Club.name) == name.lower())):
            name = f"{base} {suffix}"; suffix += 1
        club = Club(name=name, organisation_id=organisation.id, status="active", owner_user_id=user.id)
        db.add(club); db.flush()
    member = db.scalar(select(ClubMember).where(ClubMember.club_id == club.id, ClubMember.user_id == user.id))
    if member is None:
        db.add(ClubMember(club_id=club.id, user_id=user.id, role="analyst" if user.role != "administrator" else "coach"))
    licence = db.scalar(select(Licence).where(Licence.club_id == club.id, Licence.owner_type == "club").order_by(Licence.id.desc()))
    if licence is None:
        code = generate_licence_code(tier)
        licence = Licence(code_hash=hash_licence_code(code), code_last_four=normalise_licence_code(code)[-4:], tier=tier, owner_type="club", club_id=club.id, status="active", activated_at=datetime.now(timezone.utc))
        db.add(licence)
    licence.tier=tier; licence.products_json=products_json; licence.sports_json=sports_json; licence.features_json=features_json
    licence.max_devices=max_devices; licence.max_users=max_users; licence.status="active"
    return licence


@router.post("/admin/access-grants/organisations/{organisation_id}")
def grant_override(organisation_id: int, payload: GrantRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _platform_admin(admin)
    org=db.get(Organisation, organisation_id)
    if not org: raise HTTPException(status_code=404, detail="Organisation not found")
    for old in db.scalars(select(OrganisationAccessGrant).where(OrganisationAccessGrant.organisation_id==organisation_id, OrganisationAccessGrant.active.is_(True))).all():
        old.active=False; old.revoked_at=datetime.now(timezone.utc)
    grant=OrganisationAccessGrant(organisation_id=organisation_id, grant_type="override", tier=payload.tier, products_json=_dump(payload.products), sports_json=_dump(payload.sports), features_json=json.dumps(payload.features), max_devices=payload.max_devices, max_users=payload.max_users, release_channel=payload.release_channel.lower(), expires_at=payload.expires_at, created_by_user_id=admin.id)
    db.add(grant)
    db.add(AuditLog(admin_user_id=admin.id, action="access_override_granted", category="licensing", target_type="organisation", target_id=org.id, target_label=org.name, details=payload.reason or f"Temporary {payload.tier} override granted."))
    db.commit(); db.refresh(grant)
    return {"grant": grant_payload(grant), "billing_unchanged": True}


@router.delete("/admin/access-grants/organisations/{organisation_id}")
def revoke_override(organisation_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _platform_admin(admin); now=datetime.now(timezone.utc); count=0
    for grant in db.scalars(select(OrganisationAccessGrant).where(OrganisationAccessGrant.organisation_id==organisation_id, OrganisationAccessGrant.active.is_(True))).all():
        grant.active=False; grant.revoked_at=now; count+=1
    db.commit(); return {"revoked": count}


@router.get("/admin/access-grants/organisations/{organisation_id}")
def get_override(organisation_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _platform_admin(admin); return {"grant": grant_payload(current_access_grant(db, organisation_id))}


@router.post("/admin/beta-codes")
def create_beta_code(payload: BetaCodeRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _platform_admin(admin)
    if payload.release_channel.lower() not in {"stable","beta","alpha","internal"}: raise HTTPException(status_code=422, detail="Invalid release channel")
    code=_new_beta_code()
    item=BetaAccessCode(code_hash=_hash_code(code), code_last_four=code[-4:], label=payload.label, tier=payload.tier, products_json=_dump(payload.products), sports_json=_dump(payload.sports), features_json=json.dumps(payload.features), max_devices=payload.max_devices, max_users=payload.max_users, release_channel=payload.release_channel.lower(), duration_days=payload.duration_days, max_redemptions=payload.max_redemptions, expires_at=payload.expires_at, created_by_user_id=admin.id)
    db.add(item); db.commit(); db.refresh(item)
    return {"beta_code": code, "id":item.id, "expires_at":item.expires_at, "max_redemptions":item.max_redemptions}


@router.get("/admin/beta-codes")
def list_beta_codes(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _platform_admin(admin)
    rows=db.scalars(select(BetaAccessCode).order_by(BetaAccessCode.id.desc())).all()
    return {"codes":[{"id":x.id,"label":x.label,"code_last_four":x.code_last_four,"tier":x.tier,"release_channel":x.release_channel,"redemptions":x.redemption_count,"max_redemptions":x.max_redemptions,"expires_at":x.expires_at,"active":x.active} for x in rows]}


@router.delete("/admin/beta-codes/{code_id}")
def revoke_beta_code(code_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _platform_admin(admin); item=db.get(BetaAccessCode,code_id)
    if not item: raise HTTPException(status_code=404, detail="Beta code not found")
    item.active=False
    grants=db.scalars(select(OrganisationAccessGrant).where(OrganisationAccessGrant.source_beta_code_id==item.id, OrganisationAccessGrant.active.is_(True))).all()
    now=datetime.now(timezone.utc)
    for g in grants: g.active=False; g.revoked_at=now
    db.commit(); return {"revoked":True,"access_grants_revoked":len(grants)}


@router.post("/beta/redeem")
def redeem_beta_code(payload: RedeemRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.accept_beta_terms or payload.beta_terms_version != BETA_TERMS_VERSION:
        raise HTTPException(status_code=422, detail="Current FAST Beta Terms must be accepted")
    item=db.scalar(select(BetaAccessCode).where(BetaAccessCode.code_hash==_hash_code(payload.code)))
    now=datetime.now(timezone.utc)
    if not item or not item.active: raise HTTPException(status_code=404, detail="Beta code is invalid or unavailable")
    expiry=item.expires_at
    if expiry and (expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry) <= now: raise HTTPException(status_code=410, detail="Beta code has expired")
    if item.redemption_count >= item.max_redemptions: raise HTTPException(status_code=409, detail="Beta code has reached its redemption limit")
    org=db.get(Organisation,user.organisation_id) if user.organisation_id else None
    if org is None:
        base=(payload.organisation_name or f"{user.full_name or user.email} Beta").strip()[:180]
        name=base; suffix=2
        while db.scalar(select(Organisation.id).where(func.lower(Organisation.name)==name.lower())):
            name=f"{base} {suffix}"[:180]; suffix+=1
        org=Organisation(name=name, contact_name=user.full_name, contact_email=user.email, subscription_tier="FAST Beta", sports_json=item.sports_json, max_seats=item.max_users, status="active", deployment_ring="beta")
        db.add(org); db.flush(); user.organisation_id=org.id; user.role="administrator"
    existing=db.scalar(select(BetaCodeRedemption).where(BetaCodeRedemption.beta_code_id==item.id, BetaCodeRedemption.organisation_id==org.id))
    if existing: raise HTTPException(status_code=409, detail="This organisation has already redeemed this beta code")
    for old in db.scalars(select(OrganisationAccessGrant).where(OrganisationAccessGrant.organisation_id==org.id, OrganisationAccessGrant.active.is_(True))).all():
        old.active=False; old.revoked_at=now
    grant=OrganisationAccessGrant(organisation_id=org.id, grant_type="beta", tier=item.tier, products_json=item.products_json, sports_json=item.sports_json, features_json=item.features_json, max_devices=item.max_devices, max_users=item.max_users, release_channel=item.release_channel, expires_at=now+timedelta(days=item.duration_days), source_beta_code_id=item.id, created_by_user_id=user.id)
    db.add(grant); db.flush()
    _ensure_org_runtime(db,user,org,tier=item.tier,products_json=item.products_json,sports_json=item.sports_json,features_json=item.features_json,max_devices=item.max_devices,max_users=item.max_users)
    user.products_json=item.products_json; user.sports_json=item.sports_json
    db.add(BetaCodeRedemption(beta_code_id=item.id, organisation_id=org.id, user_id=user.id, grant_id=grant.id, beta_terms_version=BETA_TERMS_VERSION))
    item.redemption_count += 1
    db.add(AuditLog(admin_user_id=user.id, action="beta_code_redeemed", category="beta", target_type="organisation", target_id=org.id, target_label=org.name, details=f"Beta code ending {item.code_last_four} redeemed; access expires {grant.expires_at.isoformat()}."))
    db.commit(); db.refresh(grant)
    return {"redeemed":True,"organisation_id":org.id,"grant":grant_payload(grant),"billing_required":False}
