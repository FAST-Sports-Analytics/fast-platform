from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import time
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jwt import InvalidTokenError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.seats import ALLOCATED_USER_STATUSES, allocated_user_count, effective_user_seat_limit, organisation_device_capacity
from app.core.security import (
    create_admin_portal_token,
    decode_token,
    generate_licence_code,
    hash_licence_code,
    hash_password,
    normalise_licence_code,
    verify_password,
)
from app.db.session import engine, get_db
from app.models import AuditLog, BillingWebhookEvent, Club, ClubMember, CrashReport, DeviceActivation, DeviceAuditLog, Licence, LicenceTemplate, Organisation, OrganisationSubscription, Product, Release, RemoteCommand, Sport, User
from app.core.config import get_settings
from app.releases import MAX_PACKAGE_BYTES as MAX_RELEASE_PACKAGE_BYTES, PACKAGES_DIR as RELEASE_PACKAGES_DIR, validate_release_package

router = APIRouter(prefix="/admin", tags=["Admin Portal"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["json"] = json
COOKIE_NAME = "fast_cloud_admin"
settings = get_settings()

SERVER_STARTED_AT = datetime.now(timezone.utc)

RELEASES_ROOT = Path(__file__).resolve().parents[1] / "releases"


def _safe_release_filename(item: Release, original_name: str) -> str:
    suffix = Path(original_name).suffix.lower()
    if suffix != ".zip":
        raise ValueError("Release packages must be ZIP files.")
    def clean(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._") or "release"
    return f"fast-{clean(item.component)}-{clean(item.version)}-{clean(item.channel)}.zip"


def _validate_release_zip(path: Path) -> None:
    validate_release_package(path)



def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _format_bytes(value: int) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def _probe_hub() -> tuple[str, str, float | None]:
    started = time.perf_counter()
    for path in ("/health", "/matches"):
        try:
            with urlopen(f"http://127.0.0.1:8765{path}", timeout=0.45) as response:
                latency = (time.perf_counter() - started) * 1000
                if 200 <= response.status < 500:
                    return "healthy", "FAST Hub is reachable on port 8765.", latency
        except (OSError, URLError):
            continue
    return "warning", "FAST Hub is not currently reachable from FAST Cloud.", None


def _system_health_snapshot(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    components: list[dict] = []

    db_started = time.perf_counter()
    try:
        db.execute(select(1)).scalar_one()
        db_latency = (time.perf_counter() - db_started) * 1000
        components.append({"name": "Database", "status": "healthy", "detail": "Connected and responding.", "metric": f"{db_latency:.1f} ms"})
    except Exception as exc:
        db_latency = None
        components.append({"name": "Database", "status": "critical", "detail": f"Database check failed: {exc}", "metric": "Unavailable"})

    components.insert(0, {
        "name": "FAST Cloud API", "status": "healthy",
        "detail": "The administration service is online.",
        "metric": _format_duration((now - SERVER_STARTED_AT).total_seconds()),
    })

    hub_status, hub_detail, hub_latency = _probe_hub()
    components.append({"name": "FAST Hub", "status": hub_status, "detail": hub_detail, "metric": f"{hub_latency:.1f} ms" if hub_latency is not None else "Offline"})

    database_size = 0
    database_path = "Managed database"
    url = str(engine.url)
    if url.startswith("sqlite") and engine.url.database:
        candidate = Path(engine.url.database)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        database_path = str(candidate)
        try:
            database_size = candidate.stat().st_size
        except OSError:
            pass

    disk = shutil.disk_usage(Path.cwd())
    disk_free_percent = (disk.free / disk.total * 100) if disk.total else 0.0
    disk_status = "healthy" if disk_free_percent >= 15 else ("warning" if disk_free_percent >= 7 else "critical")
    components.append({
        "name": "Storage", "status": disk_status,
        "detail": f"{_format_bytes(disk.free)} free of {_format_bytes(disk.total)} on the Cloud host.",
        "metric": f"{disk_free_percent:.1f}% free",
    })

    recent_cutoff = now - timedelta(minutes=15)
    day_cutoff = now - timedelta(days=1)
    active_devices = db.scalar(select(func.count(DeviceActivation.id)).where(DeviceActivation.active.is_(True))) or 0
    recent_devices = db.scalar(select(func.count(DeviceActivation.id)).where(DeviceActivation.active.is_(True), DeviceActivation.last_validated_at >= recent_cutoff)) or 0
    recent_users = db.scalar(select(func.count(User.id)).where(User.last_login_at >= day_cutoff)) or 0
    active_licences = db.scalar(select(func.count(Licence.id)).where(Licence.status == "active")) or 0
    licence_warnings = db.scalar(select(func.count(Licence.id)).where(Licence.status.in_(["expired", "suspended", "revoked"]))) or 0
    audit_today = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.created_at >= day_cutoff)) or 0

    overall = "healthy"
    if any(item["status"] == "critical" for item in components):
        overall = "critical"
    elif any(item["status"] == "warning" for item in components) or licence_warnings:
        overall = "warning"

    return {
        "generated_at": now, "overall": overall, "components": components,
        "uptime": _format_duration((now - SERVER_STARTED_AT).total_seconds()),
        "database_latency_ms": db_latency, "database_size": _format_bytes(database_size),
        "database_path": database_path, "disk_free": _format_bytes(disk.free),
        "disk_total": _format_bytes(disk.total), "disk_free_percent": disk_free_percent,
        "active_devices": active_devices, "recent_devices": recent_devices,
        "recent_users": recent_users, "active_licences": active_licences,
        "licence_warnings": licence_warnings, "audit_today": audit_today,
    }



def current_admin(request: Request, db: Session) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        user_id = decode_token(token, expected_type="admin_portal")
    except (InvalidTokenError, ValueError, KeyError):
        return None
    user = db.get(User, user_id)
    if not user or user.status != "active":
        return None
    if not (user.is_admin or (user.organisation_id is not None and (user.role or "").lower() == "administrator")):
        return None
    return user


def _record_audit(
    db: Session, admin: User, action: str, category: str, *,
    target_type: str | None = None, target_id: int | None = None,
    target_label: str | None = None, details: str = "",
) -> None:
    db.add(AuditLog(
        admin_user_id=admin.id, action=action, category=category,
        target_type=target_type, target_id=target_id,
        target_label=(target_label or None), details=(details or None),
    ))


def require_portal_admin(request: Request, db: Session) -> User:
    user = current_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Administrator login required")
    if user.organisation_id is not None:
        path = request.url.path.rstrip("/")
        allowed_prefix = f"/admin/organisations/{user.organisation_id}"
        if path not in {"/admin/dashboard", "/admin/my-organisation", "/admin/logout"} and not path.startswith(allowed_prefix):
            raise HTTPException(status_code=403, detail="This administrator can only manage their own organisation")
    return user


def _ensure_organisation_access(admin: User, organisation_id: int) -> None:
    if admin.organisation_id is not None and admin.organisation_id != organisation_id:
        raise HTTPException(status_code=403, detail="You cannot manage another organisation")


@router.get("", response_class=HTMLResponse)
def admin_root(request: Request, db: Session = Depends(get_db)):
    if current_admin(request, db):
        return RedirectResponse("/admin/dashboard", status_code=303)
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if current_admin(request, db):
        return RedirectResponse("/admin/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user or not verify_password(password, user.password_hash) or not user.is_admin:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Incorrect administrator email or password."},
            status_code=401,
        )
    response = RedirectResponse("/admin/dashboard", status_code=303)
    session_seconds = max(1, settings.admin_portal_session_days) * 24 * 60 * 60
    response.set_cookie(
        COOKIE_NAME,
        create_admin_portal_token(user.id),
        httponly=True,
        samesite="lax",
        secure=settings.environment.lower() == "production",
        max_age=session_seconds,
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    if admin.organisation_id is not None:
        return RedirectResponse(f"/admin/organisations/{admin.organisation_id}", status_code=303)
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    licences = db.scalars(select(Licence).order_by(Licence.created_at.desc())).all()
    active_devices = db.scalar(
        select(func.count(DeviceActivation.id)).where(DeviceActivation.active.is_(True))
    ) or 0
    stats = {
        "users": len(users),
        "licences": len(licences),
        "active_licences": sum(1 for item in licences if item.status == "active"),
        "active_devices": active_devices,
        "clubs": db.scalar(select(func.count(Club.id))) or 0,
        "organisations": db.scalar(select(func.count(Organisation.id))) or 0,
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "admin": admin,
            "licences": licences,
            "stats": stats,
            "json": json,
        },
    )


@router.get("/users/new", response_class=HTMLResponse)
def new_user_page(request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    clubs = db.scalars(select(Club).where(Club.status == "active").order_by(Club.name)).all()
    licences = db.scalars(select(Licence).where(
        Licence.owner_type == "individual", Licence.user_id.is_(None)
    ).order_by(Licence.created_at.desc())).all()
    return templates.TemplateResponse(
        request, "user_form.html",
        {"admin": admin, "clubs": clubs, "licences": licences, "error": "", "values": {}},
    )


@router.post("/users/new", response_class=HTMLResponse)
def create_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    email_verified: str = Form("false"),
    club_id: str = Form(""),
    licence_id: str = Form(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    clean_email = email.lower().strip()
    clean_name = full_name.strip()
    values = {"full_name": clean_name, "email": clean_email, "club_id": club_id, "licence_id": licence_id}
    clubs = db.scalars(select(Club).where(Club.status == "active").order_by(Club.name)).all()
    licences = db.scalars(select(Licence).where(
        Licence.owner_type == "individual", Licence.user_id.is_(None)
    ).order_by(Licence.created_at.desc())).all()
    error = ""
    if not clean_email or "@" not in clean_email:
        error = "Enter a valid email address."
    elif len(password) < 8:
        error = "The temporary password must be at least 8 characters."
    elif db.scalar(select(User).where(func.lower(User.email) == clean_email)):
        error = "An account already exists for that email address."
    if error:
        return templates.TemplateResponse(request, "user_form.html", {
            "admin": admin, "clubs": clubs, "licences": licences, "error": error, "values": values
        }, status_code=400)
    user = User(
        email=clean_email, full_name=clean_name or None, password_hash=hash_password(password),
        email_verified=email_verified == "true", status="active", is_admin=False,
    )
    db.add(user)
    db.flush()
    if club_id:
        club = db.get(Club, int(club_id))
        if club:
            db.add(ClubMember(club_id=club.id, user_id=user.id, role="coach"))
    if licence_id:
        licence = db.get(Licence, int(licence_id))
        if licence and licence.owner_type == "individual" and licence.user_id is None:
            licence.user_id = user.id
    _record_audit(db, admin, "created", "user", target_type="user", target_id=user.id, target_label=user.email, details="Customer account created.")
    db.commit()
    return RedirectResponse(f"/admin/users/{user.id}?message=User+created.", status_code=303)


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    q: str = Query(""),
    status: str = Query("all"),
    verified: str = Query("all"),
    role: str = Query("all"),
    message: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    statement = select(User).order_by(User.created_at.desc())

    search = q.strip()
    if search:
        term = f"%{search}%"
        statement = statement.where(
            or_(User.email.ilike(term), User.full_name.ilike(term))
        )
    if status in {"active", "suspended"}:
        statement = statement.where(User.status == status)
    if verified in {"yes", "no"}:
        statement = statement.where(User.email_verified.is_(verified == "yes"))
    if role == "admin":
        statement = statement.where(User.is_admin.is_(True))
    elif role == "customer":
        statement = statement.where(User.is_admin.is_(False))

    users = db.scalars(statement).all()
    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = db.scalar(
        select(func.count(User.id)).where(User.status == "active")
    ) or 0
    verified_users = db.scalar(
        select(func.count(User.id)).where(User.email_verified.is_(True))
    ) or 0
    admin_users = db.scalar(
        select(func.count(User.id)).where(User.is_admin.is_(True))
    ) or 0

    return templates.TemplateResponse(
        request,
        "users.html",
        {
            "admin": admin,
            "users": users,
            "filters": {
                "q": search,
                "status": status,
                "verified": verified,
                "role": role,
            },
            "stats": {
                "total": total_users,
                "active": active_users,
                "verified": verified_users,
                "admins": admin_users,
            },
            "message": message,
            "error": error,
        },
    )


@router.post("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    request: Request,
    status: str = Form(...),
    return_to: str = Form("/admin/users"),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    if status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="Invalid user status")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and status == "suspended":
        return RedirectResponse(
            "/admin/users?error=You+cannot+suspend+your+own+administrator+account.",
            status_code=303,
        )
    user.status = status
    _record_audit(db, admin, status, "user", target_type="user", target_id=user.id, target_label=user.email, details=f"User status changed to {status}.")
    db.commit()
    return RedirectResponse(f"{return_to}?message=User+status+updated.", status_code=303)


@router.post("/users/{user_id}/verify")
def verify_user_email(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.email_verified = True
    user.verification_token = None
    _record_audit(db, require_portal_admin(request, db), "verified", "user", target_type="user", target_id=user.id, target_label=user.email, details="Email marked as verified.")
    db.commit()
    return RedirectResponse("/admin/users?message=Email+marked+as+verified.", status_code=303)


@router.post("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    request: Request,
    is_admin: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id != admin.id or is_admin != "true":
        return RedirectResponse(
            "/admin/users?error=Only+the+primary+FAST+Administrator+can+hold+administrator+access.",
            status_code=303,
        )
    return RedirectResponse("/admin/users?message=Administrator+access+unchanged.", status_code=303)


def _hard_delete_user(db: Session, user: User) -> None:
    """Delete a customer account and records that cannot outlive that account."""
    licence_ids = [item.id for item in db.scalars(select(Licence).where(Licence.user_id == user.id)).all()]
    if licence_ids:
        device_ids = [item.id for item in db.scalars(select(DeviceActivation).where(DeviceActivation.licence_id.in_(licence_ids))).all()]
        if device_ids:
            db.query(RemoteCommand).filter(RemoteCommand.device_activation_id.in_(device_ids)).delete(synchronize_session=False)
            db.query(DeviceAuditLog).filter(DeviceAuditLog.device_activation_id.in_(device_ids)).delete(synchronize_session=False)
        db.query(DeviceActivation).filter(DeviceActivation.licence_id.in_(licence_ids)).delete(synchronize_session=False)
        db.query(Licence).filter(Licence.id.in_(licence_ids)).delete(synchronize_session=False)
    db.query(ClubMember).filter(ClubMember.user_id == user.id).delete(synchronize_session=False)
    db.query(Club).filter(Club.owner_user_id == user.id).update({Club.owner_user_id: None}, synchronize_session=False)
    db.query(CrashReport).filter(CrashReport.user_id == user.id).update({CrashReport.user_id: None}, synchronize_session=False)
    db.query(Release).filter(Release.created_by_user_id == user.id).update({Release.created_by_user_id: None}, synchronize_session=False)
    db.query(RemoteCommand).filter(RemoteCommand.requested_by_user_id == user.id).delete(synchronize_session=False)
    db.query(DeviceAuditLog).filter(DeviceAuditLog.admin_user_id == user.id).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.admin_user_id == user.id).delete(synchronize_session=False)
    db.delete(user)


@router.post("/users/{user_id}/delete")
def delete_user(
    user_id: int,
    request: Request,
    return_to: str = Form("/admin/users"),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        return RedirectResponse(
            "/admin/users?error=You+cannot+delete+your+own+administrator+account.",
            status_code=303,
        )
    label = user.email
    _record_audit(db, admin, "deleted", "user", target_type="user", target_id=user.id, target_label=label, details="Customer account permanently deleted; licences, memberships and active device records removed.")
    _hard_delete_user(db, user)
    db.commit()
    separator = "&" if "?" in return_to else "?"
    return RedirectResponse(f"{return_to}{separator}message=User+deleted+permanently.", status_code=303)



@router.get("/users/{user_id}", response_class=HTMLResponse)
def user_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    clubs = db.scalars(select(Club).where(Club.status == "active").order_by(Club.name)).all()
    available_licences = db.scalars(select(Licence).where(
        Licence.owner_type == "individual",
        or_(Licence.user_id.is_(None), Licence.user_id == user.id),
    ).order_by(Licence.created_at.desc())).all()
    return templates.TemplateResponse(
        request,
        "user_profile.html",
        {
            "admin": admin, "user": user, "json": json, "clubs": clubs,
            "available_licences": available_licences,
            "message": request.query_params.get("message", ""),
            "error": request.query_params.get("error", ""),
        },
    )


@router.post("/users/{user_id}/edit")
def edit_user(
    user_id: int, request: Request, full_name: str = Form(""), email: str = Form(...),
    club_id: str = Form(""), licence_id: str = Form(""), db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    clean_email = email.lower().strip()
    duplicate = db.scalar(select(User).where(func.lower(User.email) == clean_email, User.id != user.id))
    if not clean_email or "@" not in clean_email or duplicate:
        return RedirectResponse(f"/admin/users/{user_id}?error=Enter+a+unique+valid+email+address.", status_code=303)
    user.full_name = full_name.strip() or None
    user.email = clean_email
    for membership in list(user.club_memberships):
        db.delete(membership)
    if club_id:
        club = db.get(Club, int(club_id))
        if club:
            db.add(ClubMember(club_id=club.id, user_id=user.id, role="coach"))
    current_individual = list(user.licences)
    selected_id = int(licence_id) if licence_id else None
    for licence in current_individual:
        if licence.owner_type == "individual" and licence.id != selected_id:
            licence.user_id = None
    if selected_id:
        licence = db.get(Licence, selected_id)
        if licence and licence.owner_type == "individual" and (licence.user_id in {None, user.id}):
            licence.user_id = user.id
    _record_audit(db, require_portal_admin(request, db), "updated", "user", target_type="user", target_id=user.id, target_label=user.email, details="User details, club or licence assignment updated.")
    db.commit()
    return RedirectResponse(f"/admin/users/{user_id}?message=User+details+updated.", status_code=303)


@router.post("/users/{user_id}/password")
def reset_user_password(
    user_id: int, request: Request, password: str = Form(...), db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if len(password) < 8:
        return RedirectResponse(f"/admin/users/{user_id}?error=Password+must+be+at+least+8+characters.", status_code=303)
    user.password_hash = hash_password(password)
    _record_audit(db, require_portal_admin(request, db), "password_reset", "user", target_type="user", target_id=user.id, target_label=user.email, details="Temporary password updated by FAST Administrator.")
    db.commit()
    return RedirectResponse(f"/admin/users/{user_id}?message=Temporary+password+updated.", status_code=303)



@router.get("/my-organisation")
def my_organisation(request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    if admin.organisation_id is None:
        return RedirectResponse("/admin/organisations", status_code=303)
    return RedirectResponse(f"/admin/organisations/{admin.organisation_id}", status_code=303)

@router.get("/organisations", response_class=HTMLResponse)
def organisations_page(
    request: Request,
    q: str = Query(""),
    message: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    statement = select(Organisation).order_by(Organisation.created_at.desc())
    search = q.strip()
    if search:
        term = f"%{search}%"
        statement = statement.where(or_(Organisation.name.ilike(term), Organisation.contact_email.ilike(term)))
    organisations = db.scalars(statement).all()
    all_sports = db.scalars(select(Sport).where(Sport.active.is_(True)).order_by(Sport.name)).all()
    return templates.TemplateResponse(request, "organisations.html", {
        "admin": admin, "organisations": organisations, "all_sports": all_sports, "q": search,
        "message": message, "error": error,
    })


@router.post("/organisations")
def create_organisation(
    request: Request,
    name: str = Form(...),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    country: str = Form(""),
    notes: str = Form(""),
    subscription_tier: str = Form("FAST Professional"),
    sports: list[str] = Form(default=[]),
    max_seats: int = Form(1),
    expires_at: str = Form(""),
    logo_url: str = Form(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    clean_name = name.strip()
    if not clean_name:
        return RedirectResponse("/admin/organisations?error=Enter+an+organisation+name.", status_code=303)
    if db.scalar(select(Organisation).where(func.lower(Organisation.name) == clean_name.lower())):
        return RedirectResponse("/admin/organisations?error=That+organisation+already+exists.", status_code=303)
    expiry = None
    if expires_at.strip():
        try:
            expiry = datetime.fromisoformat(expires_at.strip()).replace(tzinfo=timezone.utc)
        except ValueError:
            return RedirectResponse("/admin/organisations?error=Enter+a+valid+expiry+date.", status_code=303)
    item = Organisation(name=clean_name, contact_name=contact_name.strip() or None,
                        contact_email=contact_email.strip().lower() or None,
                        country=country.strip() or None, notes=notes.strip() or None,
                        subscription_tier=subscription_tier.strip() or "FAST Professional",
                        sports_json=json.dumps(sorted(set(sports))),
                        max_seats=max(1, min(max_seats, 500)), expires_at=expiry,
                        logo_url=logo_url.strip() or None)
    db.add(item)
    db.flush()
    _record_audit(db, admin, "created", "organisation", target_type="organisation", target_id=item.id, target_label=item.name, details="Organisation created.")
    db.commit()
    db.refresh(item)
    return RedirectResponse(f"/admin/organisations/{item.id}?message=Organisation+created.", status_code=303)


@router.get("/organisations/{organisation_id}", response_class=HTMLResponse)
def organisation_profile(
    organisation_id: int,
    request: Request,
    message: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    _ensure_organisation_access(admin, organisation_id)
    organisation = db.get(Organisation, organisation_id)
    if not organisation:
        raise HTTPException(status_code=404, detail="Organisation not found")
    unassigned_clubs = db.scalars(select(Club).where(Club.organisation_id.is_(None)).order_by(Club.name)).all()
    licence_ids = [licence.id for club in organisation.clubs for licence in club.licences]
    organisation_users = db.scalars(select(User).where(User.organisation_id == organisation.id).order_by(User.full_name, User.email)).all()
    selected_sports = json.loads(getattr(organisation, "sports_json", "[]") or "[]")
    all_sports = db.scalars(select(Sport).where(Sport.active.is_(True)).order_by(Sport.name)).all()
    active_devices = 0
    if licence_ids:
        active_devices = db.scalar(select(func.count(DeviceActivation.id)).where(
            DeviceActivation.licence_id.in_(licence_ids), DeviceActivation.active.is_(True)
        )) or 0
    organisation_devices = db.scalars(select(DeviceActivation).join(Licence).join(Club).where(Club.organisation_id == organisation.id).order_by(DeviceActivation.last_validated_at.desc())).all()
    organisation_audit = db.scalars(select(AuditLog).where(AuditLog.admin_user_id.in_([u.id for u in organisation_users] or [-1])).order_by(AuditLog.created_at.desc()).limit(50)).all()
    licence_products = sorted({product for club in organisation.clubs for licence in club.licences if licence.status == "active" for product in json.loads(licence.products_json or "[]")})
    licence_sports = sorted({sport for club in organisation.clubs for licence in club.licences if licence.status == "active" for sport in json.loads(licence.sports_json or "[]")})
    # The organisation profile template renders both licensed user and device
    # capacities.  Use the same entitlement helpers as the API so the admin
    # portal reflects the effective subscription/licence limits instead of
    # falling back to an em dash when no explicit template context is supplied.
    seat_limit = effective_user_seat_limit(db, organisation)
    seats_used = allocated_user_count(db, organisation.id)
    device_capacity = organisation_device_capacity(organisation)

    # Build the seat-holder table from the same active/invited status rules used
    # by enforcement. Removed/suspended users remain visible in the access table
    # for auditability, but they must not consume a licensed seat.
    licensed_users = []
    candidate_users: dict[int, User] = {user.id: user for user in organisation_users}
    for club in organisation.clubs:
        for membership in club.members:
            candidate_users[membership.user_id] = membership.user
    for candidate in sorted(candidate_users.values(), key=lambda item: ((item.full_name or '').lower(), item.email.lower())):
        if str(candidate.status or '').lower() not in ALLOCATED_USER_STATUSES:
            continue
        direct = candidate.organisation_id == organisation.id
        memberships = [
            membership for membership in candidate.club_memberships
            if membership.club and membership.club.organisation_id == organisation.id
        ]
        if direct or memberships:
            licensed_users.append({"user": candidate, "direct": direct, "memberships": memberships})

    return templates.TemplateResponse(request, "organisation_profile.html", {
        "admin": admin, "organisation": organisation, "unassigned_clubs": unassigned_clubs if admin.organisation_id is None else [],
        "active_devices": active_devices, "seats_used": seats_used,
        "seat_limit": seat_limit, "device_capacity": device_capacity,
        "licensed_users": licensed_users,
        "selected_sports": selected_sports, "all_sports": all_sports, "organisation_users": organisation_users,
        "organisation_devices": organisation_devices, "organisation_audit": organisation_audit,
        "licence_products": licence_products, "licence_sports": licence_sports,
        "message": message, "error": error,
    })


@router.post("/organisations/{organisation_id}/users")
def create_organisation_user(
    organisation_id: int, request: Request, full_name: str = Form(...), email: str = Form(...),
    password: str = Form(...), role: str = Form("analyst"), products: list[str] = Form([]), sports: list[str] = Form([]), db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    _ensure_organisation_access(admin, organisation_id)
    organisation = db.get(Organisation, organisation_id)
    if not organisation:
        raise HTTPException(status_code=404, detail="Organisation not found")
    clean_email = email.lower().strip()
    valid_roles = {"administrator", "analyst", "coach", "scout"}
    if role not in valid_roles or "@" not in clean_email or len(password) < 8:
        return RedirectResponse(f"/admin/organisations/{organisation_id}?error=Enter+valid+user+details+and+an+8-character+password.", status_code=303)
    if db.scalar(select(User).where(func.lower(User.email) == clean_email)):
        return RedirectResponse(f"/admin/organisations/{organisation_id}?error=That+email+already+has+an+account.", status_code=303)
    seats = db.scalar(select(func.count(User.id)).where(User.organisation_id == organisation.id, User.status == "active")) or 0
    if seats >= organisation.max_seats:
        return RedirectResponse(f"/admin/organisations/{organisation_id}?error=This+organisation+has+used+all+available+seats.", status_code=303)
    user = User(email=clean_email, full_name=full_name.strip() or None, password_hash=hash_password(password),
                email_verified=True, status="active", role=role, is_admin=False, organisation_id=organisation.id,
                products_json=json.dumps(products), sports_json=json.dumps(sports), must_change_password=True, invited_at=datetime.now(timezone.utc))
    db.add(user); db.flush()
    _record_audit(db, admin, "created", "organisation_user", target_type="user", target_id=user.id, target_label=user.email, details=f"{role.title()} created for {organisation.name}.")
    db.commit()
    return RedirectResponse(f"/admin/organisations/{organisation_id}?message=User+created.", status_code=303)


@router.post("/organisations/{organisation_id}/users/{user_id}")
def update_organisation_user(organisation_id: int, user_id: int, request: Request, full_name: str = Form(""),
                             role: str = Form("analyst"), status: str = Form("active"), products: list[str] = Form([]), sports: list[str] = Form([]), db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    _ensure_organisation_access(admin, organisation_id)
    user = db.get(User, user_id)
    if not user or user.organisation_id != organisation_id:
        raise HTTPException(status_code=404, detail="Organisation user not found")
    valid_roles = {"administrator", "analyst", "coach", "scout"}
    user.full_name = full_name.strip() or None
    user.role = role if role in valid_roles else "analyst"
    user.is_admin = False
    user.status = status if status in {"active", "suspended"} else "active"
    user.products_json = json.dumps(products)
    user.sports_json = json.dumps(sports)
    _record_audit(db, admin, "updated", "organisation_user", target_type="user", target_id=user.id, target_label=user.email, details=f"Role: {user.role}; status: {user.status}.")
    db.commit()
    return RedirectResponse(f"/admin/organisations/{organisation_id}?message=User+updated.", status_code=303)



@router.post("/organisations/{organisation_id}/devices/{device_id}/deactivate")
def organisation_deactivate_device(organisation_id: int, device_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    _ensure_organisation_access(admin, organisation_id)
    device = db.scalar(select(DeviceActivation).join(Licence).join(Club).where(DeviceActivation.id == device_id, Club.organisation_id == organisation_id))
    if not device:
        raise HTTPException(status_code=404, detail="Organisation device not found")
    device.active = False
    db.add(DeviceAuditLog(device_activation_id=device.id, admin_user_id=admin.id, action="deactivated", details="Device deactivated by organisation administrator."))
    _record_audit(db, admin, "device_deactivated", "organisation_device", target_type="device", target_id=device.id, target_label=device.device_name or device.device_id, details="Organisation administrator reclaimed a device seat.")
    db.commit()
    return RedirectResponse(f"/admin/organisations/{organisation_id}?message=Device+deactivated.", status_code=303)

@router.post("/organisations/{organisation_id}/update")
def update_organisation(
    organisation_id: int,
    request: Request,
    name: str = Form(...),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    country: str = Form(""),
    notes: str = Form(""),
    subscription_tier: str = Form("FAST Professional"),
    sports: list[str] = Form(default=[]),
    max_seats: int = Form(1),
    expires_at: str = Form(""),
    logo_url: str = Form(""),
    status: str = Form("active"),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    item = db.get(Organisation, organisation_id)
    if not item:
        raise HTTPException(status_code=404, detail="Organisation not found")
    item.name = name.strip() or item.name
    item.contact_name = contact_name.strip() or None
    item.contact_email = contact_email.strip().lower() or None
    item.country = country.strip() or None
    item.notes = notes.strip() or None
    item.subscription_tier = subscription_tier.strip() or "FAST Professional"
    item.sports_json = json.dumps(sorted(set(sports)))
    item.max_seats = max(1, min(max_seats, 500))
    item.logo_url = logo_url.strip() or None
    if expires_at.strip():
        try:
            item.expires_at = datetime.fromisoformat(expires_at.strip()).replace(tzinfo=timezone.utc)
        except ValueError:
            return RedirectResponse(f"/admin/organisations/{organisation_id}?error=Enter+a+valid+expiry+date.", status_code=303)
    else:
        item.expires_at = None
    item.status = status if status in {"active", "suspended", "archived"} else "active"
    _record_audit(db, admin, "updated", "organisation", target_type="organisation", target_id=item.id, target_label=item.name, details=f"Organisation details updated. Status: {item.status}.")
    db.commit()
    return RedirectResponse(f"/admin/organisations/{item.id}?message=Organisation+updated.", status_code=303)


@router.post("/organisations/{organisation_id}/delete")
def delete_organisation(
    organisation_id: int,
    request: Request,
    confirm_name: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    if admin.organisation_id is not None:
        raise HTTPException(status_code=403, detail="Only the FAST platform administrator can delete organisations")
    organisation = db.get(Organisation, organisation_id)
    if not organisation:
        raise HTTPException(status_code=404, detail="Organisation not found")
    if confirm_name.strip() != organisation.name:
        return RedirectResponse(f"/admin/organisations/{organisation_id}?error=Organisation+name+did+not+match.+Nothing+was+deleted.", status_code=303)

    subscription = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation.id))
    if subscription and subscription.external_subscription_id and str(subscription.status or '').lower() not in {"cancelled", "expired"}:
        return RedirectResponse(
            f"/admin/organisations/{organisation_id}?error=This+organisation+still+has+a+Stripe+subscription.+Cancel+or+expire+the+billing+subscription+before+permanent+deletion.",
            status_code=303,
        )

    label = organisation.name
    _record_audit(db, admin, "deleted", "organisation", target_type="organisation", target_id=organisation.id, target_label=label, details="Organisation permanently deleted from FAST Cloud.")

    # Keep billing/crash diagnostics usable without retaining the organisation row.
    db.query(BillingWebhookEvent).filter(BillingWebhookEvent.organisation_id == organisation.id).update({BillingWebhookEvent.organisation_id: None, BillingWebhookEvent.matched: False}, synchronize_session=False)
    db.query(CrashReport).filter(CrashReport.organisation_id == organisation.id).update({CrashReport.organisation_id: None}, synchronize_session=False)
    if subscription:
        db.delete(subscription)

    clubs = db.scalars(select(Club).where(Club.organisation_id == organisation.id)).all()
    for club in clubs:
        licence_ids = [item.id for item in db.scalars(select(Licence).where(Licence.club_id == club.id)).all()]
        if licence_ids:
            device_ids = [item.id for item in db.scalars(select(DeviceActivation).where(DeviceActivation.licence_id.in_(licence_ids))).all()]
            if device_ids:
                db.query(RemoteCommand).filter(RemoteCommand.device_activation_id.in_(device_ids)).delete(synchronize_session=False)
                db.query(DeviceAuditLog).filter(DeviceAuditLog.device_activation_id.in_(device_ids)).delete(synchronize_session=False)
            db.query(DeviceActivation).filter(DeviceActivation.licence_id.in_(licence_ids)).delete(synchronize_session=False)
            db.query(Licence).filter(Licence.id.in_(licence_ids)).delete(synchronize_session=False)
        db.query(ClubMember).filter(ClubMember.club_id == club.id).delete(synchronize_session=False)
        db.delete(club)

    users = db.scalars(select(User).where(User.organisation_id == organisation.id)).all()
    for user in users:
        if user.id == admin.id:
            continue
        _hard_delete_user(db, user)

    db.delete(organisation)
    db.commit()
    return RedirectResponse("/admin/organisations?message=Organisation+deleted+permanently.", status_code=303)


@router.post("/organisations/{organisation_id}/clubs")
def assign_club_to_organisation(
    organisation_id: int,
    request: Request,
    club_id: int = Form(...),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    organisation = db.get(Organisation, organisation_id)
    club = db.get(Club, club_id)
    if not organisation or not club:
        raise HTTPException(status_code=404, detail="Organisation or club not found")
    club.organisation_id = organisation.id
    _record_audit(db, require_portal_admin(request, db), "club_assigned", "organisation", target_type="organisation", target_id=organisation.id, target_label=organisation.name, details=f"{club.name} assigned to organisation.")
    db.commit()
    return RedirectResponse(f"/admin/organisations/{organisation.id}?message=Club+assigned.", status_code=303)


@router.get("/clubs", response_class=HTMLResponse)
def clubs_page(
    request: Request,
    message: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    clubs = db.scalars(select(Club).order_by(Club.created_at.desc())).all()
    organisations = db.scalars(select(Organisation).where(Organisation.status == "active").order_by(Organisation.name)).all()
    users = db.scalars(select(User).where(User.status == "active").order_by(User.full_name, User.email)).all()
    return templates.TemplateResponse(
        request,
        "clubs.html",
        {"admin": admin, "clubs": clubs, "organisations": organisations, "users": users, "message": message, "error": error},
    )


@router.post("/clubs")
def create_club(
    request: Request,
    name: str = Form(...),
    owner_user_id: str = Form(""),
    organisation_id: str = Form(""),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    club_name = name.strip()
    if not club_name:
        return RedirectResponse("/admin/clubs?error=Enter+a+club+name.", status_code=303)
    if db.scalar(select(Club).where(func.lower(Club.name) == club_name.lower())):
        return RedirectResponse("/admin/clubs?error=A+club+with+that+name+already+exists.", status_code=303)
    owner_id = int(owner_user_id) if owner_user_id.isdigit() else None
    org_id = int(organisation_id) if organisation_id.isdigit() else None
    club = Club(name=club_name, owner_user_id=owner_id, organisation_id=org_id)
    db.add(club)
    db.flush()
    if owner_id:
        db.add(ClubMember(club_id=club.id, user_id=owner_id, role="owner"))
    db.commit()
    return RedirectResponse(f"/admin/clubs/{club.id}?message=Club+created.", status_code=303)


@router.get("/clubs/{club_id}", response_class=HTMLResponse)
def club_profile(
    club_id: int,
    request: Request,
    message: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    club = db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    users = db.scalars(select(User).where(User.status == "active").order_by(User.full_name, User.email)).all()
    organisations = db.scalars(select(Organisation).where(Organisation.status == "active").order_by(Organisation.name)).all()
    member_ids = {member.user_id for member in club.members}
    available_users = [user for user in users if user.id not in member_ids]
    return templates.TemplateResponse(
        request,
        "club_profile.html",
        {"admin": admin, "club": club, "organisations": organisations, "available_users": available_users, "message": message, "error": error},
    )


@router.post("/clubs/{club_id}/update")
def update_club(
    club_id: int,
    request: Request,
    name: str = Form(...),
    owner_user_id: str = Form(""),
    status: str = Form("active"),
    organisation_id: str = Form(""),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    club = db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    club.name = name.strip() or club.name
    club.status = status if status in {"active", "suspended"} else "active"
    club.organisation_id = int(organisation_id) if organisation_id.isdigit() else None
    owner_id = int(owner_user_id) if owner_user_id.isdigit() else None
    club.owner_user_id = owner_id
    for member in club.members:
        if member.role == "owner" and member.user_id != owner_id:
            member.role = "coach"
    if owner_id and not any(m.user_id == owner_id for m in club.members):
        db.add(ClubMember(club_id=club.id, user_id=owner_id, role="owner"))
    elif owner_id:
        next(m for m in club.members if m.user_id == owner_id).role = "owner"
    db.commit()
    return RedirectResponse(f"/admin/clubs/{club.id}?message=Club+updated.", status_code=303)


@router.post("/clubs/{club_id}/members")
def add_club_member(
    club_id: int,
    request: Request,
    user_id: int = Form(...),
    role: str = Form("coach"),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    club = db.get(Club, club_id)
    user = db.get(User, user_id)
    if not club or not user:
        raise HTTPException(status_code=404, detail="Club or user not found")
    if any(member.user_id == user_id for member in club.members):
        return RedirectResponse(f"/admin/clubs/{club_id}?error=User+is+already+a+member.", status_code=303)
    valid_role = role if role in {"analyst", "coach"} else "coach"
    db.add(ClubMember(club_id=club_id, user_id=user_id, role=valid_role))
    db.commit()
    return RedirectResponse(f"/admin/clubs/{club_id}?message=Member+added.", status_code=303)


@router.post("/clubs/{club_id}/members/{member_id}/role")
def update_club_member_role(
    club_id: int,
    member_id: int,
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    member = db.get(ClubMember, member_id)
    if not member or member.club_id != club_id:
        raise HTTPException(status_code=404, detail="Membership not found")

    club = db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    if member.role == "owner" or club.owner_user_id == member.user_id:
        return RedirectResponse(
            f"/admin/clubs/{club_id}?error=The+club+owner+role+is+managed+from+the+Primary+contact+field.",
            status_code=303,
        )

    if role not in {"analyst", "coach"}:
        return RedirectResponse(
            f"/admin/clubs/{club_id}?error=Choose+either+Analyst+or+Coach.",
            status_code=303,
        )

    if member.role == role:
        return RedirectResponse(
            f"/admin/clubs/{club_id}?message=Member+role+unchanged.",
            status_code=303,
        )

    old_role = member.role
    member.role = role
    label = member.user.full_name or member.user.email
    _record_audit(
        db,
        admin,
        "updated",
        "club",
        target_type="club_member",
        target_id=member.id,
        target_label=label,
        details=f"Club membership role changed from {old_role} to {role} for {club.name}.",
    )
    db.commit()
    return RedirectResponse(
        f"/admin/clubs/{club_id}?message=Member+role+updated.",
        status_code=303,
    )


@router.post("/clubs/{club_id}/members/{member_id}/remove")
def remove_club_member(club_id: int, member_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    member = db.get(ClubMember, member_id)
    if not member or member.club_id != club_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    club = db.get(Club, club_id)
    if club and club.owner_user_id == member.user_id:
        return RedirectResponse(f"/admin/clubs/{club_id}?error=Assign+a+different+owner+before+removing+this+member.", status_code=303)
    label = member.user.full_name or member.user.email
    club_name = club.name if club else f"Club {club_id}"
    _record_audit(
        db,
        admin,
        "removed",
        "club",
        target_type="club_member",
        target_id=member.id,
        target_label=label,
        details=f"Member removed from {club_name}.",
    )
    db.delete(member)
    db.commit()
    return RedirectResponse(f"/admin/clubs/{club_id}?message=Member+removed.", status_code=303)


@router.get("/licences", response_class=HTMLResponse)
def licences_page(
    request: Request,
    q: str = Query(""),
    owner_type: str = Query("all"),
    status: str = Query("all"),
    message: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    statement = select(Licence).order_by(Licence.created_at.desc())
    search = q.strip()
    if search:
        term = f"%{search}%"
        statement = statement.outerjoin(User, Licence.user_id == User.id).outerjoin(Club, Licence.club_id == Club.id).where(
            or_(Licence.tier.ilike(term), User.email.ilike(term), User.full_name.ilike(term), Club.name.ilike(term), Licence.code_last_four.ilike(term))
        )
    if owner_type in {"individual", "club"}:
        statement = statement.where(Licence.owner_type == owner_type)
    if status in {"unused", "active", "suspended", "revoked", "expired"}:
        statement = statement.where(Licence.status == status)
    licences = db.scalars(statement).all()
    templates_list = db.scalars(select(LicenceTemplate).order_by(LicenceTemplate.owner_type, LicenceTemplate.name)).all()
    stats = {
        "total": db.scalar(select(func.count(Licence.id))) or 0,
        "individual": db.scalar(select(func.count(Licence.id)).where(Licence.owner_type == "individual")) or 0,
        "club": db.scalar(select(func.count(Licence.id)).where(Licence.owner_type == "club")) or 0,
        "active": db.scalar(select(func.count(Licence.id)).where(Licence.status == "active")) or 0,
    }
    return templates.TemplateResponse(
        request,
        "licences.html",
        {
            "admin": admin, "licences": licences, "licence_templates": templates_list,
            "stats": stats, "filters": {"q": search, "owner_type": owner_type, "status": status},
            "message": message, "error": error, "json": json,
        },
    )


@router.get("/licences/new", response_class=HTMLResponse)
def new_licence_page(
    request: Request,
    template_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    return _licence_form_context(request, admin, db, selected_template_id=template_id)


def _licence_form_context(
    request: Request,
    admin: User,
    db: Session,
    *,
    generated_code: str | None = None,
    error: str | None = None,
    selected_template_id: int | None = None,
    status_code: int = 200,
):
    users = db.scalars(select(User).where(User.status == "active").order_by(User.full_name, User.email)).all()
    clubs = db.scalars(select(Club).where(Club.status == "active").order_by(Club.name)).all()
    catalogue_products = db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.name)).all()
    catalogue_sports = db.scalars(select(Sport).where(Sport.active.is_(True)).order_by(Sport.name)).all()
    licence_templates = db.scalars(select(LicenceTemplate).where(LicenceTemplate.active.is_(True)).order_by(LicenceTemplate.owner_type, LicenceTemplate.name)).all()
    selected_template = db.get(LicenceTemplate, selected_template_id) if selected_template_id else None
    return templates.TemplateResponse(
        request,
        "licence_form.html",
        {
            "admin": admin, "generated_code": generated_code, "error": error,
            "users": users, "clubs": clubs, "products": catalogue_products, "sports": catalogue_sports,
            "licence_templates": licence_templates, "selected_template": selected_template, "json": json,
        },
        status_code=status_code,
    )


@router.post("/licences/new", response_class=HTMLResponse)
def new_licence_submit(
    request: Request,
    owner_type: str = Form("individual"),
    template_id: str = Form(""),
    tier: str = Form(...),
    user_id: str = Form(""),
    club_id: str = Form(""),
    products: list[str] = Form(default=[]),
    sports: list[str] = Form(default=[]),
    max_devices: int = Form(1),
    max_users: int = Form(1),
    expiry_mode: str = Form("date"),
    expires_at: str = Form(""),
    duration_days: int = Form(365),
    renewable: str = Form("true"),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    if owner_type not in {"individual", "club"}:
        return _licence_form_context(request, admin, db, error="Choose an individual or club owner type.", status_code=400)
    if not products:
        return _licence_form_context(request, admin, db, error="Select at least one product.", status_code=400)

    selected_user_id = int(user_id) if user_id.isdigit() else None
    selected_club_id = int(club_id) if club_id.isdigit() else None
    if owner_type == "individual" and selected_club_id:
        selected_club_id = None
    if owner_type == "club" and selected_user_id:
        selected_user_id = None

    expiry = None
    now = datetime.now(timezone.utc)
    if expiry_mode == "date" and expires_at.strip():
        try:
            expiry = datetime.fromisoformat(expires_at).replace(tzinfo=timezone.utc)
        except ValueError:
            return _licence_form_context(request, admin, db, error="Enter a valid expiry date.", status_code=400)
    elif expiry_mode == "duration":
        expiry = now + timedelta(days=max(1, min(duration_days, 3650)))
    elif expiry_mode != "never":
        return _licence_form_context(request, admin, db, error="Choose a valid expiry option.", status_code=400)

    code = generate_licence_code(tier)
    licence = Licence(
        code_hash=hash_licence_code(code),
        code_last_four=normalise_licence_code(code)[-4:],
        tier=tier.strip(),
        products_json=json.dumps(sorted(set(products))),
        sports_json=json.dumps(sorted(set(sports))),
        expires_at=expiry,
        max_devices=max(1, min(max_devices, 50)),
        max_users=max(1, min(max_users, 500)) if owner_type == "club" else 1,
        owner_type=owner_type,
        user_id=selected_user_id,
        club_id=selected_club_id,
        template_id=int(template_id) if template_id.isdigit() else None,
        renewable=renewable == "true",
    )
    db.add(licence)
    db.flush()
    _record_audit(db, admin, "created", "licence", target_type="licence", target_id=licence.id, target_label=f"{licence.tier} ••••{licence.code_last_four}", details="Licence created.")
    db.commit()
    return _licence_form_context(request, admin, db, generated_code=code)


@router.post("/licences/templates")
def create_licence_template(
    request: Request,
    name: str = Form(...),
    owner_type: str = Form("individual"),
    tier: str = Form(...),
    products: list[str] = Form(default=[]),
    sports: list[str] = Form(default=[]),
    default_max_devices: int = Form(1),
    default_max_users: int = Form(1),
    default_duration_days: str = Form("365"),
    renewable: str = Form("true"),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    clean_name = name.strip()
    if not clean_name or not products or owner_type not in {"individual", "club"}:
        return RedirectResponse("/admin/licences?error=Template+name,+owner+type+and+at+least+one+product+are+required.", status_code=303)
    if db.scalar(select(LicenceTemplate).where(func.lower(LicenceTemplate.name) == clean_name.lower())):
        return RedirectResponse("/admin/licences?error=A+template+with+that+name+already+exists.", status_code=303)
    days = int(default_duration_days) if default_duration_days.isdigit() else None
    db.add(LicenceTemplate(
        name=clean_name, owner_type=owner_type, tier=tier.strip(),
        products_json=json.dumps(sorted(set(products))), sports_json=json.dumps(sorted(set(sports))),
        default_max_devices=max(1, min(default_max_devices, 50)),
        default_max_users=max(1, min(default_max_users, 500)) if owner_type == "club" else 1,
        default_duration_days=days, renewable=renewable == "true",
    ))
    db.commit()
    return RedirectResponse("/admin/licences?message=Licence+template+created.", status_code=303)


@router.post("/licences/templates/{template_id}/status")
def update_template_status(
    template_id: int, request: Request, active: str = Form(...), db: Session = Depends(get_db)
):
    require_portal_admin(request, db)
    item = db.get(LicenceTemplate, template_id)
    if not item:
        raise HTTPException(status_code=404, detail="Licence template not found")
    item.active = active == "true"
    db.commit()
    return RedirectResponse("/admin/licences?message=Template+status+updated.", status_code=303)



@router.get("/licences/{licence_id}/edit", response_class=HTMLResponse)
def edit_licence_page(
    licence_id: int,
    request: Request,
    message: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    licence = db.get(Licence, licence_id)
    if not licence:
        raise HTTPException(status_code=404, detail="Licence not found")
    users = db.scalars(select(User).where(User.status == "active").order_by(User.full_name, User.email)).all()
    clubs = db.scalars(select(Club).where(Club.status == "active").order_by(Club.name)).all()
    products = db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.name)).all()
    sports = db.scalars(select(Sport).where(Sport.active.is_(True)).order_by(Sport.name)).all()
    return templates.TemplateResponse(request, "licence_edit.html", {
        "admin": admin, "licence": licence, "users": users, "clubs": clubs,
        "products": products, "sports": sports, "message": message, "error": error,
        "selected_products": json.loads(licence.products_json),
        "selected_sports": json.loads(licence.sports_json),
    })


@router.post("/licences/{licence_id}/edit")
def edit_licence_submit(
    licence_id: int,
    request: Request,
    owner_type: str = Form("individual"),
    tier: str = Form(...),
    user_id: str = Form(""),
    club_id: str = Form(""),
    products: list[str] = Form(default=[]),
    sports: list[str] = Form(default=[]),
    max_devices: int = Form(1),
    max_users: int = Form(1),
    expires_at: str = Form(""),
    never_expires: str = Form("false"),
    renewable: str = Form("false"),
    status: str = Form("active"),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    licence = db.get(Licence, licence_id)
    if not licence:
        raise HTTPException(status_code=404, detail="Licence not found")
    if owner_type not in {"individual", "club"} or status not in {"unused", "active", "suspended", "revoked", "expired"}:
        return RedirectResponse(f"/admin/licences/{licence_id}/edit?error=Invalid+licence+settings.", status_code=303)
    if not products:
        return RedirectResponse(f"/admin/licences/{licence_id}/edit?error=Select+at+least+one+product.", status_code=303)
    expiry = None
    if never_expires != "true" and expires_at.strip():
        try:
            expiry = datetime.fromisoformat(expires_at).replace(tzinfo=timezone.utc)
        except ValueError:
            return RedirectResponse(f"/admin/licences/{licence_id}/edit?error=Enter+a+valid+expiry+date.", status_code=303)
    licence.owner_type = owner_type
    licence.user_id = int(user_id) if owner_type == "individual" and user_id.isdigit() else None
    licence.club_id = int(club_id) if owner_type == "club" and club_id.isdigit() else None
    licence.tier = tier.strip() or "FAST Professional"
    licence.products_json = json.dumps(sorted(set(products)))
    licence.sports_json = json.dumps(sorted(set(sports)))
    licence.max_devices = max(1, min(max_devices, 50))
    licence.max_users = max(1, min(max_users, 500)) if owner_type == "club" else 1
    licence.expires_at = expiry
    licence.renewable = renewable == "true"
    licence.status = status
    if status == "revoked":
        for device in licence.devices:
            device.active = False
    admin = require_portal_admin(request, db)
    _record_audit(db, admin, "updated", "licence", target_type="licence", target_id=licence.id, target_label=f"{licence.tier} ••••{licence.code_last_four}", details=f"Products, sports, limits, owner, expiry or status updated. Status: {status}.")
    db.commit()
    return RedirectResponse(f"/admin/licences/{licence_id}/edit?message=Licence+saved.", status_code=303)


@router.post("/licences/{licence_id}/reset-devices")
def reset_licence_devices(
    licence_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    licence = db.get(Licence, licence_id)
    if not licence:
        raise HTTPException(status_code=404, detail="Licence not found")
    for device in licence.devices:
        device.active = False
    _record_audit(db, require_portal_admin(request, db), "devices_reset", "licence", target_type="licence", target_id=licence.id, target_label=f"{licence.tier} ••••{licence.code_last_four}", details="All device activations reset.")
    db.commit()
    return RedirectResponse(f"/admin/licences/{licence_id}/edit?message=Device+activations+reset.", status_code=303)


@router.post("/licences/{licence_id}/status")
def update_licence_status(
    licence_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    if status not in {"unused", "active", "suspended", "revoked", "expired"}:
        raise HTTPException(status_code=400, detail="Invalid licence status")
    licence = db.get(Licence, licence_id)
    if not licence:
        raise HTTPException(status_code=404, detail="Licence not found")
    licence.status = status
    if status == "revoked":
        for device in licence.devices:
            device.active = False
    _record_audit(db, require_portal_admin(request, db), status, "licence", target_type="licence", target_id=licence.id, target_label=f"{licence.tier} ••••{licence.code_last_four}", details=f"Licence status changed to {status}.")
    db.commit()
    return RedirectResponse("/admin/licences?message=Licence+status+updated.", status_code=303)


@router.post("/licences/{licence_id}/renew")
def renew_licence(
    licence_id: int,
    request: Request,
    days: int = Form(365),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    licence = db.get(Licence, licence_id)
    if not licence:
        raise HTTPException(status_code=404, detail="Licence not found")
    if not licence.renewable:
        return RedirectResponse("/admin/licences?error=This+licence+is+not+renewable.", status_code=303)
    now = datetime.now(timezone.utc)
    current = licence.expires_at
    if current and current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    base = current if current and current > now else now
    licence.expires_at = base + timedelta(days=max(1, min(days, 3650)))
    if licence.status == "expired":
        licence.status = "active" if (licence.user_id or licence.club_id) else "unused"
    _record_audit(db, require_portal_admin(request, db), "renewed", "licence", target_type="licence", target_id=licence.id, target_label=f"{licence.tier} ••••{licence.code_last_four}", details=f"Licence extended by {max(1, min(days, 3650))} days.")
    db.commit()
    return RedirectResponse("/admin/licences?message=Licence+renewed.", status_code=303)


@router.post("/licences/{licence_id}/assign")
def assign_licence(
    licence_id: int,
    request: Request,
    owner_type: str = Form(...),
    owner_id: str = Form(""),
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    licence = db.get(Licence, licence_id)
    if not licence:
        raise HTTPException(status_code=404, detail="Licence not found")
    owner_pk = int(owner_id) if owner_id.isdigit() else None
    if owner_type == "individual":
        licence.owner_type, licence.user_id, licence.club_id, licence.max_users = "individual", owner_pk, None, 1
    elif owner_type == "club":
        licence.owner_type, licence.club_id, licence.user_id = "club", owner_pk, None
    else:
        return RedirectResponse("/admin/licences?error=Invalid+licence+owner+type.", status_code=303)
    db.commit()
    return RedirectResponse("/admin/licences?message=Licence+owner+updated.", status_code=303)





@router.get("/releases", response_class=HTMLResponse)
def releases_page(
    request: Request, q: str = Query(""), component: str = Query("all"),
    channel: str = Query("all"), status: str = Query("all"),
    message: str = Query(""), error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    statement = select(Release).order_by(Release.created_at.desc())
    search = q.strip()
    if search:
        term = f"%{search}%"
        statement = statement.where(or_(
            Release.version.ilike(term), Release.component.ilike(term),
            Release.release_notes.ilike(term), Release.package_filename.ilike(term),
        ))
    if component != "all":
        statement = statement.where(Release.component == component)
    if channel != "all":
        normalised_channel = "internal" if channel == "alpha" else channel
        statement = statement.where(Release.channel == normalised_channel)
    if status != "all":
        statement = statement.where(Release.status == status)
    releases = db.scalars(statement).all()

    all_components = [value for value in db.scalars(select(Release.component).distinct().order_by(Release.component)).all() if value]
    standard_components = ["launcher", "analysis", "viewer", "hub"]
    components = list(dict.fromkeys(standard_components + all_components))

    latest = {}
    for release_channel in ("stable", "beta", "internal"):
        latest_item = db.scalar(
            select(Release)
            .where(Release.channel == release_channel, Release.status == "published")
            .order_by(Release.published_at.desc(), Release.created_at.desc())
            .limit(1)
        )
        latest[release_channel] = latest_item

    # H2C-A: build a component/channel release-history matrix and attach the
    # latest audit activity to every visible release. This keeps the release
    # inventory operationally useful without requiring a separate page.
    published_history = db.scalars(
        select(Release)
        .where(Release.status == "published")
        .order_by(Release.component, Release.published_at.desc(), Release.created_at.desc())
    ).all()
    history_by_component: dict[str, dict[str, Release]] = {}
    for item in published_history:
        component_history = history_by_component.setdefault(item.component, {})
        component_history.setdefault(item.channel, item)

    visible_ids = [item.id for item in releases]
    release_activity: dict[int, list[AuditLog]] = {release_id: [] for release_id in visible_ids}
    if visible_ids:
        activity_rows = db.scalars(
            select(AuditLog)
            .where(AuditLog.target_type == "release", AuditLog.target_id.in_(visible_ids))
            .order_by(AuditLog.created_at.desc())
        ).all()
        for activity in activity_rows:
            if activity.target_id in release_activity and len(release_activity[activity.target_id]) < 4:
                release_activity[activity.target_id].append(activity)

    telemetry_actions = [
        "update_offered", "update_download_started", "update_download_completed",
        "update_verification_passed", "update_install_started", "update_install_completed",
        "update_install_failed", "update_restart_succeeded", "update_rollback_triggered",
        "launcher_self_update_succeeded", "launcher_self_update_failed",
    ]
    telemetry_rows = db.scalars(
        select(AuditLog).where(AuditLog.category == "release", AuditLog.action.in_(telemetry_actions))
        .order_by(AuditLog.created_at.desc()).limit(250)
    ).all()
    telemetry_counts = {action: 0 for action in telemetry_actions}
    for row in telemetry_rows:
        telemetry_counts[row.action] = telemetry_counts.get(row.action, 0) + 1
    update_analytics = {
        "offered": telemetry_counts.get("update_offered", 0),
        "downloads": telemetry_counts.get("update_download_completed", 0),
        "installed": telemetry_counts.get("update_install_completed", 0) + telemetry_counts.get("launcher_self_update_succeeded", 0),
        "failed": telemetry_counts.get("update_install_failed", 0) + telemetry_counts.get("launcher_self_update_failed", 0),
        "rollbacks": telemetry_counts.get("update_rollback_triggered", 0),
        "recent": telemetry_rows[:20],
    }

    stats = {
        "total": db.scalar(select(func.count(Release.id))) or 0,
        "draft": db.scalar(select(func.count(Release.id)).where(Release.status == "draft")) or 0,
        "published": db.scalar(select(func.count(Release.id)).where(Release.status == "published")) or 0,
        "archived": db.scalar(select(func.count(Release.id)).where(Release.status == "archived")) or 0,
        "withdrawn": db.scalar(select(func.count(Release.id)).where(Release.status == "withdrawn")) or 0,
        "latest": latest,
    }
    return templates.TemplateResponse(request, "releases.html", {
        "admin": admin, "releases": releases, "stats": stats, "message": message, "error": error,
        "filters": {"q": search, "component": component, "channel": channel, "status": status},
        "components": components,
        "channels": ["internal", "beta", "stable"],
        "channel_labels": {"stable": "Stable", "beta": "Beta", "internal": "Alpha"},
        "deployment_rings": ["development", "internal", "beta", "pilot", "production"],
        "history_by_component": history_by_component,
        "release_activity": release_activity,
        "format_bytes": _format_bytes,
        "package_exists": lambda release: bool(release.package_filename and (RELEASE_PACKAGES_DIR / Path(release.package_filename).name).is_file()),
        "update_analytics": update_analytics,
    })


@router.post("/releases")
def create_release(
    request: Request, component: str = Form(...), version: str = Form(...),
    channel: str = Form("internal"), release_notes: str = Form(""),
    product_target: str = Form("all"), minimum_launcher_version: str = Form(""),
    deployment_ring: str = Form("development"), rollout_percentage: int = Form(100), rollout_notes: str = Form(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    component = component.strip().lower().replace("fast ", "").replace(" ", "_")
    channel = channel.strip().lower()
    channel = "internal" if channel == "alpha" else channel
    version = version.strip()
    if not component or not all(ch.isalnum() or ch in {"_", "-"} for ch in component):
        return RedirectResponse("/admin/releases?error=Invalid+component.", status_code=303)
    if channel not in {"stable", "beta", "internal"}:
        return RedirectResponse("/admin/releases?error=Invalid+release+channel.", status_code=303)
    if not version:
        return RedirectResponse("/admin/releases?error=Version+is+required.", status_code=303)
    duplicate = db.scalar(select(Release).where(
        Release.component == component, Release.version == version, Release.channel == channel
    ))
    if duplicate:
        return RedirectResponse("/admin/releases?error=That+component+version+already+exists+in+this+channel.", status_code=303)
    deployment_ring = deployment_ring.strip().lower()
    if deployment_ring not in {"development", "internal", "beta", "pilot", "production"}:
        deployment_ring = "development"
    item = Release(
        component=component, version=version, channel=channel, status="draft", deployment_ring=deployment_ring, rollout_percentage=max(0, min(100, rollout_percentage)), rollout_status="active", rollout_notes=rollout_notes.strip() or None,
        release_notes=release_notes.strip() or None, product_target=product_target.strip().lower() or "all",
        minimum_launcher_version=minimum_launcher_version.strip() or None, created_by_user_id=admin.id,
    )
    db.add(item)
    db.flush()
    _record_audit(db, admin, "created", "release", target_type="release", target_id=item.id,
                  target_label=f"{component} {version}", details=f"Draft release created in {channel} channel.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Draft+release+created.", status_code=303)


@router.post("/releases/{release_id}/update")
def update_release(
    release_id: int, request: Request, version: str = Form(...), channel: str = Form(...),
    release_notes: str = Form(""), product_target: str = Form("all"),
    minimum_launcher_version: str = Form(""), deployment_ring: str = Form("development"), rollout_percentage: int = Form(100), rollout_notes: str = Form(""), db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status != "draft":
        return RedirectResponse("/admin/releases?error=Only+draft+releases+can+be+edited.", status_code=303)
    channel = channel.strip().lower()
    channel = "internal" if channel == "alpha" else channel
    version = version.strip()
    if channel not in {"stable", "beta", "internal"} or not version:
        return RedirectResponse("/admin/releases?error=Invalid+release+details.", status_code=303)
    duplicate = db.scalar(select(Release).where(
        Release.id != item.id, Release.component == item.component,
        Release.version == version, Release.channel == channel
    ))
    if duplicate:
        return RedirectResponse("/admin/releases?error=That+component+version+already+exists+in+this+channel.", status_code=303)
    item.version, item.channel = version, channel
    item.deployment_ring = deployment_ring.strip().lower() if deployment_ring.strip().lower() in {"development", "internal", "beta", "pilot", "production"} else "development"
    item.release_notes = release_notes.strip() or None
    item.rollout_percentage = max(0, min(100, rollout_percentage))
    item.rollout_notes = rollout_notes.strip() or None
    item.product_target = product_target.strip().lower() or "all"
    item.minimum_launcher_version = minimum_launcher_version.strip() or None
    item.updated_at = datetime.now(timezone.utc)
    _record_audit(db, admin, "updated", "release", target_type="release", target_id=item.id,
                  target_label=f"{item.component} {item.version}", details="Draft release details updated.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Draft+release+updated.", status_code=303)


@router.post("/releases/{release_id}/package")
async def upload_release_package(
    release_id: int, request: Request, package: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status != "draft":
        return RedirectResponse("/admin/releases?error=Only+draft+releases+can+accept+packages.", status_code=303)
    try:
        filename = _safe_release_filename(item, package.filename or "")
    except ValueError as exc:
        return RedirectResponse(f"/admin/releases?error={str(exc).replace(' ', '+')}", status_code=303)

    RELEASE_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    temporary = RELEASE_PACKAGES_DIR / f".{filename}.uploading"
    final_path = RELEASE_PACKAGES_DIR / filename
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as output:
            while chunk := await package.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_RELEASE_PACKAGE_BYTES:
                    raise ValueError("The release package exceeds the 2 GB upload limit.")
                digest.update(chunk)
                output.write(chunk)
        _validate_release_zip(temporary)
        if item.package_filename and item.package_filename != filename:
            old_path = RELEASE_PACKAGES_DIR / Path(item.package_filename).name
            old_path.unlink(missing_ok=True)
        temporary.replace(final_path)
    except (OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        return RedirectResponse(f"/admin/releases?error={str(exc).replace(' ', '+')}", status_code=303)
    finally:
        await package.close()

    item.package_filename = filename
    item.package_sha256 = digest.hexdigest()
    item.package_size = size
    item.updated_at = datetime.now(timezone.utc)
    _record_audit(
        db, admin, "uploaded", "release", target_type="release", target_id=item.id,
        target_label=f"{item.component} {item.version}",
        details=f"Package {filename} uploaded ({_format_bytes(size)}; SHA-256 {item.package_sha256}).",
    )
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+package+uploaded+and+verified.", status_code=303)


@router.post("/releases/{release_id}/package/restore")
async def restore_release_package(
    release_id: int, request: Request, package: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Restore a missing package file for an existing published release.

    This recovery path deliberately preserves the release identity, channel, ring,
    rollout and published status. It only recreates the package artifact and
    refreshes its integrity metadata.
    """
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status != "published":
        return RedirectResponse("/admin/releases?error=Package+recovery+is+only+available+for+published+releases.", status_code=303)
    if not item.package_filename:
        return RedirectResponse("/admin/releases?error=This+release+has+no+package+filename+to+restore.", status_code=303)

    expected_name = Path(item.package_filename).name
    final_path = RELEASE_PACKAGES_DIR / expected_name
    package_existed = final_path.is_file()

    RELEASE_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    temporary = RELEASE_PACKAGES_DIR / f".{expected_name}.restoring"
    digest = hashlib.sha256()
    size = 0
    try:
        temporary.unlink(missing_ok=True)
        with temporary.open("wb") as output:
            while chunk := await package.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_RELEASE_PACKAGE_BYTES:
                    raise ValueError("The release package exceeds the 2 GB upload limit.")
                digest.update(chunk)
                output.write(chunk)
        # Validate the incoming artifact before touching the currently published
        # package. os.replace() then performs an atomic swap on the same volume,
        # so a failed upload/validation can never leave the release half-written.
        _validate_release_zip(temporary)
        os.replace(temporary, final_path)
    except (OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        return RedirectResponse(f"/admin/releases?error={str(exc).replace(' ', '+')}", status_code=303)
    finally:
        await package.close()

    previous_sha256 = item.package_sha256
    item.package_sha256 = digest.hexdigest()
    item.package_size = size
    item.updated_at = datetime.now(timezone.utc)
    checksum_changed = bool(previous_sha256 and previous_sha256 != item.package_sha256)
    action = "package_replaced" if package_existed else "package_recovered"
    verb = "Replaced" if package_existed else "Recovered"
    integrity_note = (
        "checksum changed; release integrity metadata updated to the verified replacement"
        if checksum_changed
        else "checksum matched the existing release record"
    )
    _record_audit(
        db, admin, action, "release", target_type="release", target_id=item.id,
        target_label=f"{item.component} {item.version}",
        details=f"{verb} published package {expected_name} ({_format_bytes(size)}; SHA-256 {item.package_sha256}); {integrity_note}.",
    )
    db.commit()
    message = "Published+release+package+replaced+and+verified." if package_existed else "Published+release+package+restored+and+verified."
    return RedirectResponse(f"/admin/releases?message={message}", status_code=303)


@router.post("/releases/{release_id}/package/delete")
def delete_release_package(release_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status != "draft":
        return RedirectResponse("/admin/releases?error=Published+release+packages+cannot+be+removed+here.", status_code=303)
    filename = item.package_filename
    if filename:
        (RELEASE_PACKAGES_DIR / Path(filename).name).unlink(missing_ok=True)
    item.package_filename = None
    item.package_sha256 = None
    item.package_size = None
    item.updated_at = datetime.now(timezone.utc)
    _record_audit(db, admin, "deleted", "release", target_type="release", target_id=item.id,
                  target_label=f"{item.component} {item.version}", details="Draft release package removed.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+package+removed.", status_code=303)


@router.get("/releases/{release_id}/package")
def download_release_package_admin(release_id: int, request: Request, db: Session = Depends(get_db)):
    require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item or not item.package_filename:
        raise HTTPException(status_code=404, detail="Release package not found")
    path = RELEASE_PACKAGES_DIR / Path(item.package_filename).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Release package file is missing")
    return FileResponse(path, filename=item.package_filename, media_type="application/zip")


@router.get("/releases/{release_id}/checksum")
def download_release_checksum(release_id: int, request: Request, db: Session = Depends(get_db)):
    require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item or not item.package_filename or not item.package_sha256:
        raise HTTPException(status_code=404, detail="Release checksum not found")
    return PlainTextResponse(
        f"{item.package_sha256}  {item.package_filename}\n",
        headers={"Content-Disposition": f'attachment; filename="{item.package_filename}.sha256"'},
    )


@router.post("/releases/{release_id}/publish")
def publish_release(release_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status != "draft":
        return RedirectResponse("/admin/releases?error=Only+draft+releases+can+be+published.", status_code=303)
    if not item.package_filename or not item.package_sha256:
        return RedirectResponse("/admin/releases?error=Upload+and+verify+a+package+before+publishing.", status_code=303)
    package_path = RELEASE_PACKAGES_DIR / Path(item.package_filename).name
    if not package_path.is_file():
        return RedirectResponse("/admin/releases?error=The+release+package+file+is+missing.", status_code=303)
    try:
        _validate_release_zip(package_path)
    except ValueError as exc:
        return RedirectResponse(f"/admin/releases?error={str(exc).replace(' ', '+')}", status_code=303)
    actual_digest = hashlib.sha256(package_path.read_bytes()).hexdigest()
    if actual_digest != item.package_sha256:
        return RedirectResponse("/admin/releases?error=Checksum+verification+failed.", status_code=303)
    now = datetime.now(timezone.utc)
    item.status = "published"
    item.published_at = now
    item.updated_at = now
    _record_audit(db, admin, "published", "release", target_type="release", target_id=item.id,
                  target_label=f"{item.component} {item.version}", details=f"Release published to {item.channel}.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+published.", status_code=303)


@router.post("/releases/{release_id}/unpublish")
def unpublish_release(release_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status != "published":
        return RedirectResponse("/admin/releases?error=Only+published+releases+can+be+unpublished.", status_code=303)
    item.status = "draft"
    item.published_at = None
    item.updated_at = datetime.now(timezone.utc)
    _record_audit(db, admin, "unpublished", "release", target_type="release", target_id=item.id,
                  target_label=f"{item.component} {item.version}", details=f"Release removed from {item.channel} channel.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+returned+to+draft.", status_code=303)


@router.post("/releases/{release_id}/promote")
def promote_release(
    release_id: int, request: Request, target_channel: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    source = db.get(Release, release_id)
    if not source:
        raise HTTPException(status_code=404, detail="Release not found")
    target_channel = target_channel.strip().lower()
    allowed = {"internal": {"beta", "stable"}, "beta": {"stable"}, "stable": set()}
    if source.status != "published" or target_channel not in allowed.get(source.channel, set()):
        return RedirectResponse("/admin/releases?error=That+release+cannot+be+promoted+to+the+selected+channel.", status_code=303)
    duplicate = db.scalar(select(Release).where(
        Release.component == source.component,
        Release.version == source.version,
        Release.channel == target_channel,
    ))
    if duplicate:
        return RedirectResponse("/admin/releases?error=That+version+already+exists+in+the+target+channel.", status_code=303)
    promoted = Release(
        component=source.component,
        version=source.version,
        channel=target_channel,
        status="published",
        release_notes=source.release_notes,
        package_filename=source.package_filename,
        package_sha256=source.package_sha256,
        package_size=source.package_size,
        product_target=source.product_target,
        minimum_launcher_version=source.minimum_launcher_version,
        deployment_ring=source.deployment_ring,
        created_by_user_id=admin.id,
        published_at=datetime.now(timezone.utc),
    )
    db.add(promoted)
    db.flush()
    _record_audit(db, admin, "promoted", "release", target_type="release", target_id=promoted.id,
                  target_label=f"{promoted.component} {promoted.version}",
                  details=f"Release promoted from {source.channel} to {target_channel}.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+promoted.", status_code=303)


@router.post("/releases/{release_id}/withdraw")
def withdraw_release(release_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status != "published":
        return RedirectResponse("/admin/releases?error=Only+published+releases+can+be+withdrawn.", status_code=303)
    item.status = "withdrawn"
    item.updated_at = datetime.now(timezone.utc)
    _record_audit(db, admin, "withdrawn", "release", target_type="release", target_id=item.id,
                  target_label=f"{item.component} {item.version}",
                  details=f"Release withdrawn from the {item.channel} channel. Existing packages remain available for audit and rollback.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+withdrawn.", status_code=303)


@router.post("/releases/{release_id}/archive")
def archive_release(release_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status not in {"draft", "published"}:
        return RedirectResponse("/admin/releases?error=Release+is+already+archived.", status_code=303)
    previous = item.status
    item.status = "archived"
    item.updated_at = datetime.now(timezone.utc)
    _record_audit(db, admin, "archived", "release", target_type="release", target_id=item.id,
                  target_label=f"{item.component} {item.version}", details=f"{previous.title()} release archived.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+archived.", status_code=303)


@router.post("/releases/{release_id}/restore")
def restore_release(release_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status not in {"archived", "withdrawn"}:
        return RedirectResponse("/admin/releases?error=Only+archived+or+withdrawn+releases+can+be+restored.", status_code=303)
    item.status = "draft"
    item.published_at = None
    item.updated_at = datetime.now(timezone.utc)
    _record_audit(db, admin, "restored", "release", target_type="release", target_id=item.id,
                  target_label=f"{item.component} {item.version}", details="Archived release restored as draft.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+restored+as+draft.", status_code=303)


@router.post("/releases/{release_id}/delete")
def delete_release(release_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    if item.status not in {"draft", "archived"}:
        return RedirectResponse("/admin/releases?error=Published+releases+must+be+unpublished+or+archived+first.", status_code=303)
    label = f"{item.component} {item.version}"
    # Only remove the physical package when no other release record references it.
    if item.package_filename:
        reference_count = db.scalar(select(func.count(Release.id)).where(
            Release.id != item.id, Release.package_filename == item.package_filename
        )) or 0
        if reference_count == 0:
            (RELEASE_PACKAGES_DIR / Path(item.package_filename).name).unlink(missing_ok=True)
    db.delete(item)
    _record_audit(db, admin, "deleted", "release", target_type="release", target_id=release_id,
                  target_label=label, details="Release record deleted.")
    db.commit()
    return RedirectResponse("/admin/releases?message=Release+deleted.", status_code=303)

@router.get("/system-health", response_class=HTMLResponse)
def system_health_page(request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    health = _system_health_snapshot(db)
    return templates.TemplateResponse(
        request, "system_health.html", {"admin": admin, "health": health}
    )

@router.get("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request, q: str = Query(""), category: str = Query("all"),
    action: str = Query("all"), date_from: str = Query(""), date_to: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    statement = select(AuditLog).order_by(AuditLog.created_at.desc())
    search = q.strip()
    if search:
        term = f"%{search}%"
        statement = statement.where(or_(
            AuditLog.action.ilike(term), AuditLog.category.ilike(term),
            AuditLog.target_label.ilike(term), AuditLog.details.ilike(term),
        ))
    if category != "all":
        statement = statement.where(AuditLog.category == category)
    if action != "all":
        statement = statement.where(AuditLog.action == action)
    if date_from:
        try:
            statement = statement.where(AuditLog.created_at >= datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc))
        except ValueError:
            pass
    if date_to:
        try:
            end = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
            statement = statement.where(AuditLog.created_at < end)
        except ValueError:
            pass
    entries = db.scalars(statement.limit(1000)).all()
    categories = db.scalars(select(AuditLog.category).distinct().order_by(AuditLog.category)).all()
    actions = db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)).all()
    total = db.scalar(select(func.count(AuditLog.id))) or 0
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.created_at >= today_start)) or 0
    return templates.TemplateResponse(request, "audit.html", {
        "admin": admin, "entries": entries, "categories": categories, "actions": actions,
        "filters": {"q": search, "category": category, "action": action, "date_from": date_from, "date_to": date_to},
        "stats": {"total": total, "today": today, "shown": len(entries)},
    })


def _device_owner_label(device: DeviceActivation) -> str:
    licence = device.licence
    if licence.user:
        return licence.user.full_name or licence.user.email
    if licence.club:
        return licence.club.name
    return "Unassigned"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _device_is_online(device: DeviceActivation) -> bool:
    """Return whether an active device has checked in during the last 3 minutes."""
    last_seen = _as_utc(device.last_validated_at)
    return bool(device.active and last_seen and (datetime.now(timezone.utc) - last_seen).total_seconds() <= 180)


def _relative_time(value: datetime | None) -> str:
    timestamp = _as_utc(value)
    if timestamp is None:
        return "Never"
    seconds = max(0, int((datetime.now(timezone.utc) - timestamp).total_seconds()))
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    return timestamp.strftime("%d.%m.%Y %H:%M")


def _record_device_action(db: Session, admin: User, device: DeviceActivation | None, action: str, details: str = "") -> None:
    db.add(DeviceAuditLog(
        device_activation_id=device.id if device else None,
        admin_user_id=admin.id,
        action=action,
        details=details or None,
    ))
    _record_audit(
        db, admin, action, "device", target_type="device",
        target_id=device.id if device else None,
        target_label=(device.device_name or device.device_id) if device else "Licence devices",
        details=details,
    )


@router.get("/devices", response_class=HTMLResponse)
def devices_page(
    request: Request,
    q: str = Query(""),
    status: str = Query("all"),
    message: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    statement = select(DeviceActivation).join(Licence).order_by(DeviceActivation.last_validated_at.desc())
    search = q.strip()
    if search:
        term = f"%{search}%"
        statement = statement.outerjoin(User, Licence.user_id == User.id).outerjoin(Club, Licence.club_id == Club.id).where(
            or_(
                DeviceActivation.device_name.ilike(term),
                DeviceActivation.device_id.ilike(term),
                User.email.ilike(term),
                User.full_name.ilike(term),
                Club.name.ilike(term),
            )
        )
    if status == "active":
        statement = statement.where(DeviceActivation.active.is_(True))
    elif status == "inactive":
        statement = statement.where(DeviceActivation.active.is_(False))
    devices = db.scalars(statement).unique().all()
    audit = db.scalars(select(DeviceAuditLog).order_by(DeviceAuditLog.created_at.desc()).limit(30)).all()
    total = db.scalar(select(func.count(DeviceActivation.id))) or 0
    active = db.scalar(select(func.count(DeviceActivation.id)).where(DeviceActivation.active.is_(True))) or 0
    seat_total = db.scalar(select(func.coalesce(func.sum(Licence.max_devices), 0)).where(Licence.status == "active")) or 0
    seat_percent = min(100, round((active / seat_total) * 100)) if seat_total else 0
    remote_commands = db.scalars(
        select(RemoteCommand).order_by(RemoteCommand.created_at.desc()).limit(50)
    ).all()
    commands_by_device = {}
    for item in remote_commands:
        commands_by_device.setdefault(item.device_activation_id, []).append(item)
    actor_ids = {item.admin_user_id for item in audit} | {item.requested_by_user_id for item in remote_commands}
    actors = {}
    if actor_ids:
        actors = {user.id: (user.full_name or user.email) for user in db.scalars(select(User).where(User.id.in_(actor_ids))).all()}
    return templates.TemplateResponse(request, "devices.html", {
        "admin": admin,
        "devices": devices,
        "audit": audit,
        "filters": {"q": search, "status": status},
        "stats": {"total": total, "active": active, "inactive": total - active, "seat_total": seat_total, "seat_percent": seat_percent},
        "owner_label": _device_owner_label,
        "device_is_online": _device_is_online,
        "relative_time": _relative_time,
        "audit_actors": actors,
        "commands_by_device": commands_by_device,
        "deployment_rings": ["development", "internal", "beta", "pilot", "production"],
        "json": json,
        "message": message,
        "error": error,
    })


@router.get("/devices/{device_id}/live.json", response_class=JSONResponse)
def device_live_status(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    require_portal_admin(request, db)
    device = db.get(DeviceActivation, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        live = json.loads(device.live_status_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        live = {}
    try:
        products = json.loads(device.installed_products_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        products = {}
    commands = db.scalars(
        select(RemoteCommand).where(RemoteCommand.device_activation_id == device.id)
        .order_by(RemoteCommand.created_at.desc()).limit(12)
    ).all()
    return {
        "device_id": device.device_id,
        "name": device.device_name or device.device_id,
        "online": _device_is_online(device),
        "last_seen": _relative_time(device.last_validated_at),
        "version": device.installed_version or "",
        "channel": device.update_channel or "",
        "ring": device.deployment_ring or "production",
        "live": live,
        "products": products,
        "commands": [{
            "id": item.id, "command": item.command, "status": item.status,
            "result": item.result or "",
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "claimed_at": item.claimed_at.isoformat() if item.claimed_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        } for item in commands],
    }


@router.post("/devices/{device_id}/rename")
def rename_device(
    device_id: int,
    request: Request,
    device_name: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    device = db.get(DeviceActivation, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    clean_name = device_name.strip()[:160]
    if not clean_name:
        return RedirectResponse("/admin/devices?error=Enter+a+device+name.", status_code=303)
    old_name = device.device_name or device.device_id
    device.device_name = clean_name
    _record_device_action(db, admin, device, "renamed", f"{old_name} → {clean_name}")
    db.commit()
    return RedirectResponse("/admin/devices?message=Device+renamed.", status_code=303)


@router.post("/devices/{device_id}/status")
def update_device_status(
    device_id: int,
    request: Request,
    active: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    device = db.get(DeviceActivation, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    make_active = active == "true"
    if make_active:
        active_count = db.scalar(select(func.count(DeviceActivation.id)).where(
            DeviceActivation.licence_id == device.licence_id,
            DeviceActivation.active.is_(True),
            DeviceActivation.id != device.id,
        )) or 0
        if active_count >= device.licence.max_devices:
            return RedirectResponse("/admin/devices?error=The+licence+device+limit+has+already+been+reached.", status_code=303)
    device.active = make_active
    _record_device_action(db, admin, device, "reactivated" if make_active else "removed", "Device access restored." if make_active else "Device deactivated and no longer counts against the licence.")
    db.commit()
    return RedirectResponse("/admin/devices?message=Device+status+updated.", status_code=303)




@router.post("/devices/{device_id}/commands")
def queue_remote_device_command(
    device_id: int,
    request: Request,
    command: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    device = db.get(DeviceActivation, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    allowed = {
        "start_hub", "stop_hub", "start_analysis", "stop_analysis",
        "start_viewer", "stop_viewer", "start_scout", "stop_scout",
        "refresh_licence", "check_updates", "restart_launcher",
    }
    command = command.strip().lower()
    if command not in allowed:
        return RedirectResponse("/admin/devices?error=Unsupported+remote+command.", status_code=303)
    pending = db.scalar(select(RemoteCommand).where(
        RemoteCommand.device_activation_id == device.id,
        RemoteCommand.command == command,
        RemoteCommand.status.in_(["pending", "claimed"]),
    ))
    if pending is not None:
        return RedirectResponse("/admin/devices?error=That+command+is+already+pending.", status_code=303)
    item = RemoteCommand(
        device_activation_id=device.id, requested_by_user_id=admin.id,
        command=command, payload_json="{}", status="pending",
    )
    db.add(item)
    _record_device_action(db, admin, device, "remote_command_queued", command.replace("_", " ").title())
    db.commit()
    return RedirectResponse("/admin/devices?message=Remote+command+queued.", status_code=303)

@router.post("/devices/{device_id}/force-signout")
def force_device_signout(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    device = db.get(DeviceActivation, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.active = False
    _record_device_action(db, admin, device, "force_signout", "Device entitlement was revoked. The Launcher must authenticate and activate again.")
    db.commit()
    return RedirectResponse("/admin/devices?message=Device+signed+out.", status_code=303)


@router.post("/devices/licence/{licence_id}/reset")
def reset_devices_for_licence(
    licence_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    licence = db.get(Licence, licence_id)
    if not licence:
        raise HTTPException(status_code=404, detail="Licence not found")
    changed = 0
    for device in licence.devices:
        if device.active:
            device.active = False
            changed += 1
            _record_device_action(db, admin, device, "licence_reset", "Deactivated by licence-wide device reset.")
    db.commit()
    return RedirectResponse(f"/admin/devices?message={changed}+device+activation(s)+reset.", status_code=303)


@router.post("/devices/{device_id}/deployment-ring")
def update_device_deployment_ring(
    device_id: int, request: Request, deployment_ring: str = Form(...), db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    device = db.get(DeviceActivation, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ring = deployment_ring.strip().lower()
    if ring not in {"development", "internal", "beta", "pilot", "production"}:
        return RedirectResponse("/admin/devices?error=Invalid+deployment+ring.", status_code=303)
    device.deployment_ring = ring
    _record_device_action(db, admin, device, "deployment_ring_changed", f"Device assigned to the {ring.title()} deployment ring.")
    db.commit()
    return RedirectResponse("/admin/devices?message=Deployment+ring+updated.", status_code=303)


@router.post("/releases/{release_id}/deployment-ring")
def promote_release_deployment_ring(
    release_id: int, request: Request, deployment_ring: str = Form(...), db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    rings = ["development", "internal", "beta", "pilot", "production"]
    target = deployment_ring.strip().lower()
    if target not in rings:
        return RedirectResponse("/admin/releases?error=Invalid+deployment+ring.", status_code=303)
    current = item.deployment_ring or "development"
    if rings.index(target) < rings.index(current):
        return RedirectResponse("/admin/releases?error=Use+rollback+controls+to+move+a+release+to+an+earlier+ring.", status_code=303)
    item.deployment_ring = target
    db.add(AuditLog(admin_user_id=admin.id, action="deployment_ring_promoted", category="release", target_type="release", target_id=item.id, target_label=f"{item.component} {item.version}", details=f"Release promoted from {current.title()} to {target.title()}."))
    db.commit()
    return RedirectResponse("/admin/releases?message=Deployment+ring+updated.", status_code=303)


@router.post("/releases/{release_id}/mandatory")
def set_release_mandatory(
    request: Request, release_id: int, mandatory: str = Form("0"),
    mandatory_deadline: str = Form(""), db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if item is None:
        return RedirectResponse("/admin/releases?error=Release+not+found.", status_code=303)
    enabled = str(mandatory).lower() in {"1", "true", "yes", "on"}
    deadline = None
    if enabled and mandatory_deadline.strip():
        try:
            deadline = datetime.fromisoformat(mandatory_deadline.strip())
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        except ValueError:
            return RedirectResponse("/admin/releases?error=Invalid+mandatory+deadline.", status_code=303)
    item.mandatory = enabled
    item.mandatory_deadline = deadline
    db.add(AuditLog(admin_user_id=admin.id, action="mandatory_updated", category="release",
        target_type="release", target_id=item.id, target_label=f"{item.component} {item.version}",
        details=f"Mandatory update {'enabled' if enabled else 'disabled'}" + (f" from {deadline.isoformat()}" if deadline else ".")))
    db.commit()
    return RedirectResponse("/admin/releases?message=Mandatory+update+settings+saved.", status_code=303)


@router.post("/releases/{release_id}/rollout")
def update_release_rollout(
    release_id: int, request: Request, rollout_percentage: int = Form(...),
    rollout_action: str = Form("active"), rollout_notes: str = Form(""), db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    item = db.get(Release, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release not found")
    action = rollout_action.strip().lower()
    if action not in {"active", "paused", "stopped"}:
        action = "active"
    old_percentage = int(getattr(item, "rollout_percentage", 100) or 0)
    old_status = getattr(item, "rollout_status", "active") or "active"
    item.rollout_percentage = max(0, min(100, int(rollout_percentage)))
    item.rollout_status = action
    item.rollout_notes = rollout_notes.strip() or None
    db.add(AuditLog(admin_user_id=admin.id, action="rollout_updated", category="release", target_type="release", target_id=item.id, target_label=f"{item.component} {item.version}", details=f"Rollout changed from {old_percentage}%/{old_status} to {item.rollout_percentage}%/{item.rollout_status}."))
    db.commit()
    return RedirectResponse("/admin/releases?message=Rollout+updated.", status_code=303)


@router.get("/diagnostics", response_class=HTMLResponse)
def diagnostics_page(request: Request, db: Session = Depends(get_db)):
    admin = current_admin(request, db)
    if not admin:
        return RedirectResponse("/admin/login", status_code=303)
    incidents = db.scalars(select(CrashReport).order_by(CrashReport.last_seen_at.desc(), CrashReport.id.desc()).limit(250)).all()
    occurrences = sum(int(item.occurrence_count or 0) for item in incidents)
    versions = len({item.version for item in incidents if item.version})
    open_count = sum(1 for item in incidents if item.status in {"open", "investigating"})
    latest = incidents[0].last_seen_at if incidents else None
    return templates.TemplateResponse(request, "diagnostics.html", {
        "admin": admin, "incidents": incidents,
        "totals": {"open": open_count, "occurrences": occurrences, "versions": versions, "last_seen": latest},
    })


@router.post("/diagnostics/{incident_id}/status")
def diagnostics_status(incident_id: int, request: Request, status: str = Form(...), db: Session = Depends(get_db)):
    admin = current_admin(request, db)
    if not admin:
        return RedirectResponse("/admin/login", status_code=303)
    allowed = {"open", "investigating", "resolved", "ignored"}
    incident = db.get(CrashReport, incident_id)
    if incident and status in allowed:
        incident.status = status
        _record_audit(db, admin, action="diagnostic_status_changed", category="diagnostics", target_type="crash_report", target_id=incident.id, target_label=f"{incident.component} {incident.exception_type}", details=f"Incident marked {status}.")
        db.commit()
    return RedirectResponse("/admin/diagnostics", status_code=303)

@router.get("/subscriptions", response_class=HTMLResponse)
def subscriptions_page(request: Request, db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    if not admin.is_admin:
        return RedirectResponse("/admin/my-organisation", status_code=303)
    from app.models import OrganisationSubscription, SubscriptionPlan
    plans = db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.name)).all()
    organisations = db.scalars(select(Organisation).order_by(Organisation.name)).all()
    subscriptions = db.scalars(select(OrganisationSubscription).order_by(OrganisationSubscription.id.desc())).all()
    return templates.TemplateResponse(request, "subscriptions.html", {
        "admin": admin, "plans": plans, "organisations": organisations, "subscriptions": subscriptions,
        "active_count": sum(1 for item in subscriptions if item.status == "active"),
        "trial_count": sum(1 for item in subscriptions if item.status == "trial"),
        "risk_count": sum(1 for item in subscriptions if item.status in {"past_due", "grace_period"}),
    })


@router.post("/subscriptions/plans")
def create_subscription_plan(
    request: Request, name: str = Form(...), description: str = Form(""), monthly_price: float = Form(0),
    annual_price: float = Form(0), trial_days: int = Form(0), included_seats: int = Form(1),
    max_devices: int = Form(1), cloud_storage_gb: int = Form(0), products: str = Form(""), sports: str = Form(""),
    remote_management: str | None = Form(None), priority_support: str | None = Form(None),
    self_service_upgrades: str | None = Form(None), db: Session = Depends(get_db),
):
    admin = require_portal_admin(request, db)
    if not admin.is_admin:
        raise HTTPException(status_code=403, detail="FAST owner access required")
    from app.models import SubscriptionPlan
    clean_name = name.strip()
    if db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.name == clean_name)):
        return RedirectResponse("/admin/subscriptions?error=That+plan+already+exists.", status_code=303)
    item = SubscriptionPlan(name=clean_name, description=description.strip() or None,
        monthly_price_pence=max(0, round(monthly_price * 100)), annual_price_pence=max(0, round(annual_price * 100)),
        trial_days=max(0, trial_days), included_seats=max(1, included_seats), max_devices=max(1, max_devices),
        cloud_storage_gb=max(0, cloud_storage_gb),
        products_json=json.dumps([v.strip() for v in products.split(',') if v.strip()]),
        sports_json=json.dumps([v.strip() for v in sports.split(',') if v.strip()]),
        features_json=json.dumps({"remote_management": bool(remote_management), "priority_support": bool(priority_support)}),
        self_service_upgrades=bool(self_service_upgrades), active=True)
    db.add(item); db.flush(); _record_audit(db, admin, action="subscription_plan_created", category="billing", target_type="subscription_plan", target_id=item.id, target_label=item.name, details="Flexible subscription plan created.")
    db.commit()
    return RedirectResponse("/admin/subscriptions?message=Plan+created.", status_code=303)


@router.post("/subscriptions/assign")
def assign_subscription_plan(request: Request, organisation_id: int = Form(...), plan_id: int = Form(...),
    status: str = Form("active"), billing_interval: str = Form("monthly"), seat_override: str = Form(""), db: Session = Depends(get_db)):
    admin = require_portal_admin(request, db)
    if not admin.is_admin:
        raise HTTPException(status_code=403, detail="FAST owner access required")
    from app.models import OrganisationSubscription, SubscriptionPlan
    organisation = db.get(Organisation, organisation_id); plan = db.get(SubscriptionPlan, plan_id)
    if not organisation or not plan:
        return RedirectResponse("/admin/subscriptions?error=Organisation+or+plan+not+found.", status_code=303)
    item = db.scalar(select(OrganisationSubscription).where(OrganisationSubscription.organisation_id == organisation.id))
    if not item:
        item = OrganisationSubscription(organisation_id=organisation.id); db.add(item)
    item.plan_id = plan.id; item.status = status if status in {"trial","active","past_due","grace_period","cancelled","expired"} else "active"
    item.billing_interval = billing_interval if billing_interval in {"monthly","annual","manual"} else "monthly"
    item.seat_override = int(seat_override) if seat_override.strip().isdigit() and int(seat_override) > 0 else None
    effective_seat_limit = max(1, int(item.seat_override or plan.included_seats or 1))
    organisation.subscription_tier = plan.name
    organisation.max_seats = effective_seat_limit

    # The Admin Portal must use the same entitlement materialisation path as
    # the subscription API and Stripe synchronisation.  Updating only the
    # OrganisationSubscription row leaves the Launcher-backed Licence on the
    # previous plan (products/features/device limits), producing a mixed state
    # such as Starter with Viewer and five devices.  Import lazily to avoid
    # coupling module initialisation while keeping one canonical sync helper.
    from app.api.routes.subscriptions import _ensure_subscription_entitlements
    _ensure_subscription_entitlements(
        db, organisation, plan, quantity=1, seat_limit=effective_seat_limit
    )

    _record_audit(db, admin, action="subscription_assigned", category="billing", target_type="organisation", target_id=organisation.id, target_label=organisation.name, details=f"Assigned {plan.name} ({item.billing_interval}).")
    db.commit()
    return RedirectResponse("/admin/subscriptions?message=Subscription+assigned.", status_code=303)
