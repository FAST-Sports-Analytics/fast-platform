from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes import admin_releases, admin_summary, auth, diagnostics, licences, organisation_management, subscriptions, updates, users
from app.admin_portal import router as admin_portal_router
from app.releases import router as releases_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import migrate_schema
from app.db.seed import seed_catalogue
from app.db.session import SessionLocal, engine
from app import models  # noqa: F401

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment.lower() == "production":
        if settings.database_url.lower().startswith("sqlite"):
            raise RuntimeError(
                "FAST Cloud production must use PostgreSQL. Set FAST_CLOUD_DATABASE_URL "
                "to a postgresql+psycopg:// connection string."
            )
        if settings.jwt_secret == "development-only-change-me" or len(settings.jwt_secret) < 32:
            raise RuntimeError("FAST Cloud production requires a strong FAST_CLOUD_JWT_SECRET (32+ characters).")
        provider = (settings.email_provider or "auto").strip().lower()
        real_email_ready = bool(
            (provider in {"resend", "auto"} and settings.resend_api_key and settings.email_from_email)
            or (provider in {"smtp", "auto"} and settings.smtp_host and (settings.email_from_email or settings.smtp_from_email))
        )
        if not real_email_ready:
            raise RuntimeError("FAST Cloud production requires a configured transactional email provider.")

    Base.metadata.create_all(bind=engine)
    migrate_schema(engine)
    with SessionLocal() as db:
        seed_catalogue(db)
    yield


app = FastAPI(
    title="FAST Cloud API",
    version="0.21.0a",
    description="Authentication, licensing and administration for FAST Sports Analytics.",
    lifespan=lifespan,
)

# Browser-based account recovery on fastsportsanalytics.com needs to call
# FAST Cloud directly. Keep this allow-list intentionally narrow.
cors_origins = [
    "https://www.fastsportsanalytics.com",
    "https://fastsportsanalytics.com",
]
if settings.environment.lower() != "production":
    cors_origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)

@app.middleware("http")
async def security_headers_and_local_recovery(request: Request, call_next):
    response = await call_next(request)

    # Chromium may issue a Local/Private Network Access preflight when the
    # HTTPS website talks to a developer FAST Cloud running on loopback.
    if (
        settings.environment.lower() != "production"
        and request.headers.get("access-control-request-private-network") == "true"
    ):
        response.headers["Access-Control-Allow-Private-Network"] = "true"

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/api/v1/auth"):
        response.headers.setdefault("Cache-Control", "no-store")
    if settings.environment.lower() == "production" and request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(licences.router, prefix="/api/v1")
app.include_router(licences.admin_router, prefix="/api/v1")
app.include_router(admin_summary.router, prefix="/api/v1")
app.include_router(admin_releases.router, prefix="/api/v1")
app.include_router(updates.router, prefix="/api/v1")
app.include_router(diagnostics.router, prefix="/api/v1")
app.include_router(organisation_management.router, prefix="/api/v1")
app.include_router(subscriptions.router, prefix="/api/v1")
app.include_router(releases_router)
app.include_router(admin_portal_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
def health() -> dict:
    database_ok = True
    database_detail = "reachable"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
        database_detail = "unavailable"

    provider = (settings.email_provider or "auto").strip().lower()
    email_configured = bool(
        (provider in {"resend", "auto"} and settings.resend_api_key and settings.email_from_email)
        or (provider in {"smtp", "auto"} and settings.smtp_host and (settings.email_from_email or settings.smtp_from_email))
    )
    healthy = database_ok
    return {
        "status": "ok" if healthy else "degraded",
        "service": settings.app_name,
        "version": "0.20.0a",
        "environment": settings.environment,
        "checks": {
            "database": {"ok": database_ok, "detail": database_detail},
            "transactional_email": {"configured": email_configured, "provider": provider},
        },
    }


@app.get("/ready")
def readiness() -> dict:
    """Deployment readiness probe: succeeds only when the database is reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "service": settings.app_name, "version": "0.20.0a"}
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": settings.app_name, "version": "0.20.0a"},
        )
