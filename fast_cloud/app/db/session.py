from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

database_url = settings.database_url
if database_url.startswith("postgresql://"):
    # Railway and many managed Postgres providers expose a generic
    # postgresql:// URL. FAST Cloud uses psycopg 3, so select the
    # SQLAlchemy psycopg dialect explicitly instead of psycopg2.
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]

is_sqlite = database_url.lower().startswith("sqlite")
engine_kwargs = {
    "future": True,
    "pool_pre_ping": settings.database_pool_pre_ping,
}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_recycle"] = settings.database_pool_recycle_seconds

engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
