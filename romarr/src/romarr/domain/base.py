"""SQLAlchemy declarative base + shared mixins."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


# Spec 001 T007 — SQLAlchemy naming convention. Wired so that
# Alembic autogen produces stable, predictable constraint
# names matching the patterns used in the hand-authored
# migrations (``ck_tag_assignment_entity_type``,
# ``uq_library_name``, etc.). Without this, an autogen run
# would emit dialect-specific machine-generated names that
# change across SQLAlchemy versions.
_NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide declarative base.

    Foundation tables follow this base. Later specs may add their own
    tables under the same metadata so a single Alembic environment
    introspects the whole schema.
    """

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


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
