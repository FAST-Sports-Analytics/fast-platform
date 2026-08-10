from __future__ import annotations

from sqlalchemy import text

from app.core.config import get_settings
from app.core.storage import release_packages_dir
from app.db.session import engine


def main() -> None:
    settings = get_settings()
    failures: list[str] = []

    if settings.environment.lower() != "production":
        failures.append("FAST_CLOUD_ENV must be production.")
    if settings.database_url.lower().startswith("sqlite"):
        failures.append("Production must use PostgreSQL, not SQLite.")
    if settings.jwt_secret == "development-only-change-me" or len(settings.jwt_secret) < 32:
        failures.append("FAST_CLOUD_JWT_SECRET must be a strong 32+ character secret.")
    if not settings.public_app_url.lower().startswith("https://"):
        failures.append("FAST_CLOUD_PUBLIC_APP_URL must use HTTPS.")
    if not settings.email_from_email or not settings.resend_api_key:
        failures.append("Resend production email configuration is incomplete.")

    if failures:
        raise SystemExit("[FAST Cloud] Production preflight failed:\n- " + "\n- ".join(failures))

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise SystemExit(f"[FAST Cloud] PostgreSQL is not reachable: {exc}") from exc

    packages = release_packages_dir()
    probe = packages / ".fast-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise SystemExit(f"[FAST Cloud] Release storage is not writable: {packages}: {exc}") from exc

    print("[FAST Cloud] Production preflight passed.")
    print(f"[FAST Cloud] Release storage: {packages}")


if __name__ == "__main__":
    main()
