from __future__ import annotations

from datetime import datetime, timezone
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import OrganisationAccessGrant


def _utc(value):
    if value is None: return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def current_access_grant(db: Session, organisation_id: int | None) -> OrganisationAccessGrant | None:
    if organisation_id is None: return None
    now=datetime.now(timezone.utc)
    grants=db.scalars(select(OrganisationAccessGrant).where(OrganisationAccessGrant.organisation_id==organisation_id, OrganisationAccessGrant.active.is_(True)).order_by(OrganisationAccessGrant.id.desc())).all()
    for grant in grants:
        start=_utc(grant.starts_at); end=_utc(grant.expires_at)
        if start and start > now: continue
        if end and end <= now:
            grant.active=False
            continue
        return grant
    return None

def grant_payload(grant):
    if not grant: return None
    def loads(raw, fallback):
        try: return json.loads(raw or '')
        except (TypeError, ValueError): return fallback
    return {"id":grant.id,"grant_type":grant.grant_type,"tier":grant.tier,"products":loads(grant.products_json,[]),"sports":loads(grant.sports_json,[]),"features":loads(grant.features_json,{}),"max_devices":grant.max_devices,"max_users":grant.max_users,"release_channel":grant.release_channel,"expires_at":grant.expires_at}
