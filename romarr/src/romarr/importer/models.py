"""SQLAlchemy models for the importer feature (spec 008).

One new table — ``import_history``. The ``unidentified_dump``
column extensions live on the foundation's ORM class
(``romarr.domain.models.UnidentifiedDump``) so spec 007's search
engine and spec 009's library router can reference them without
importing this module; only the FK target on ``library_id`` is
gated by the migration since ``library`` may not exist yet.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,  # re-exported for downstream test fixtures
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_IMPORTED_VIA_CHECK = (
    "imported_via IN ('automatic','manual','rss','api','webhook','scan')"
)


class ImportHistory(Base, TimestampMixin):
    """Audit trail of every import round, success or failure.

    Append-only at the application level (no UPDATEs after creation;
    a retry produces a new row). All FKs are NULLable + ``ON DELETE
    SET NULL`` because the audit row must survive its referents.
    """

    __tablename__ = "import_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_path: Mapped[str] = mapped_column(String, nullable=False)
    dest_path: Mapped[str | None] = mapped_column(String, nullable=True)

    download_client_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("download_client.id", ondelete="SET NULL"),
        nullable=True,
    )
    download_client_native_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    game_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("game.id", ondelete="SET NULL"),
        nullable=True,
    )
    release_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("release.id", ondelete="SET NULL"),
        nullable=True,
    )
    dump_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("dump.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_hash_sha1: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    imported_via: Mapped[str] = mapped_column(String(16), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    coalesced: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    warning: Mapped[str | None] = mapped_column(String, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(String, nullable=True)
    imported_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(_IMPORTED_VIA_CHECK, name="ck_import_history_imported_via"),
        Index("idx_import_history_started_at", "started_at"),
        Index(
            "idx_import_history_release_started",
            "release_id",
            "started_at",
        ),
        Index("idx_import_history_correlation", "correlation_id"),
        Index(
            "idx_import_history_native_id", "download_client_native_id"
        ),
        Index("idx_import_history_success", "success"),
    )


__all__ = ["JSON", "ImportHistory"]
