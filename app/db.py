"""Database layer: engine, session factory and the ``Transcription`` ORM model.

The backend is chosen by the ``DATABASE_URL`` environment variable (PostgreSQL in production,
SQLite when unset). The URL is normalised so values copied from Neon, Render or Heroku work as-is.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = (os.getenv("DATABASE_URL") or "sqlite:///./transcriptions.db").strip().strip("'\"")
# Render/Heroku style URLs
for prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefix):  # use the psycopg2 driver from requirements.txt
        DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len(prefix):]
# Neon adds channel_binding=require, which some libpq builds reject; sslmode=require is enough.
DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "").replace("?channel_binding=require&", "?")

# SQLite connections are shared across FastAPI worker threads.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping replaces connections that Neon closes when it autosuspends.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models."""


class Transcription(Base):
    """One saved transcription session (a row in ``transcriptions``).

    Attributes:
        id: Auto-incrementing primary key.
        title: Short label, at most 200 characters.
        text: Full transcript (Devanagari and/or Latin script).
        language: Most frequent detected language code, or ``"auto"``.
        duration_sec: Length of the recorded audio in seconds.
        created_at: UTC timestamp set on insert.
        updated_at: UTC timestamp refreshed on every update.
    """

    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), default="Untitled")
    text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(32), default="auto")
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        """Serialise the row to a JSON-ready dict (ISO 8601 timestamps, duration rounded to 0.01 s)."""
        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "language": self.language,
            "duration_sec": round(self.duration_sec or 0, 2),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def init_db() -> None:
    """Create any missing tables. Safe to call on every startup."""
    Base.metadata.create_all(engine)
