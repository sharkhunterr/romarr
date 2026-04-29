"""SQLAlchemy declarative base + shared mixins."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Project-wide declarative base.

    Foundation tables follow this base. Later specs may add their own
    tables under the same metadata so a single Alembic environment
    introspects the whole schema.
    """


class TimestampMixin:
    """Standard ``created_at`` / ``updated_at`` columns.

    Stored as timezone-aware UTC. The application is the single writer;
    DB defaults are intentionally Python-driven for portability between
    SQLite and PostgreSQL.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
