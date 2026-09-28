"""Database engine and session factory (works with MySQL and SQLite)."""
import warnings

from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

# SQLite has no native Decimal type; MySQL does. The warning is noise for local/test runs.
warnings.filterwarnings("ignore", message=".*does \\*not\\* support Decimal.*", category=SAWarning)


def make_engine(url: str):
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
