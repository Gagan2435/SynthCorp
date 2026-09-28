"""ORM model for the app's own metadata. Generated data lives in per-run tables (see services/tables.py)."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

LongText = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    seed: Mapped[int] = mapped_column(Integer)
    inject_defects: Mapped[bool] = mapped_column(Boolean, default=False)
    config_yaml: Mapped[str] = mapped_column(LongText)
    table_prefix: Mapped[str] = mapped_column(String(20), default="")
    plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    progress: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    table_counts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    quality: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
