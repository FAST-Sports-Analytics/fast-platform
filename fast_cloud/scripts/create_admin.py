from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.migrations import migrate_schema
from app.db.session import SessionLocal, engine
from app.models import User

VALID_DEFAULT_ADMIN = "admin@fastsportsanalytics.com"
OLD_ADMIN = "admin@fastsportsanalytics.local"


def main() -> None:
    settings = get_settings()
    admin_email = settings.admin_email.lower().strip()
    if admin_email.endswith(".local"):
        print(f"Migrating invalid development administrator email {admin_email} -> {VALID_DEFAULT_ADMIN}")
        admin_email = VALID_DEFAULT_ADMIN
    Base.metadata.create_all(bind=engine)
    # The bootstrap runs before FastAPI's lifespan on Railway. Existing
    # databases therefore need schema upgrades here before ORM queries.
    migrate_schema(engine)
    with SessionLocal() as db:
        old = db.scalar(select(User).where(User.email == OLD_ADMIN))
        existing = db.scalar(select(User).where(User.email == admin_email))
        if old and not existing:
            old.email = admin_email
            existing = old
        if existing:
            existing.is_admin = True
            existing.email_verified = True
            existing.status = "active"
            if settings.environment.lower() != "production" or settings.rotate_admin_password:
                existing.password_hash = hash_password(settings.admin_password)
                print(f"Updated administrator: {existing.email}")
            else:
                print(f"Administrator already exists: {existing.email} (password unchanged)")
        else:
            db.add(User(email=admin_email,password_hash=hash_password(settings.admin_password),full_name="FAST Administrator",email_verified=True,is_admin=True))
            print(f"Created administrator: {admin_email}")
        db.commit()

if __name__ == "__main__":
    main()
