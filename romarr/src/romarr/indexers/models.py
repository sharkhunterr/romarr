"""SQLAlchemy models for the indexer feature.

Two new tables:

  - ``indexer``     — configured Newznab/Torznab indexers; API key
    encrypted at rest (re-uses :mod:`romarr.metadata.encryption`).
  - ``application`` — Prowlarr instances that have registered Romarr
    as a downstream *arr.

The ``indexer.download_client_id`` column is added without a FK
because the ``download_client`` table arrives in spec 005 — that
spec's migration adds the FK once the target table exists.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_IMPLEMENTATION_CHECK = "implementation IN ('newznab','torznab')"
_SOURCE_CHECK = "source IN ('manual','prowlarr')"
_SYNC_LEVEL_CHECK = "sync_level IN ('disabled','add_only','full_sync')"


class Indexer(Base, TimestampMixin):
    __tablename__ = "indexer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    implementation: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    categories: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    enable_rss: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_automatic_search: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    enable_interactive_search: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    tags: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    rate_limit_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )
    min_seeders: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    download_client_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    prowlarr_app_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("application.id", ondelete="SET NULL"),
        nullable=True,
    )
    seed_ratio: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    seed_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    priority_indexer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    result_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100
    )
    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_health_error: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "implementation", "url", name="uq_indexer_impl_url"
        ),
        Index("idx_indexer_source", "source"),
        CheckConstraint(_IMPLEMENTATION_CHECK, name="ck_indexer_implementation"),
        CheckConstraint(_SOURCE_CHECK, name="ck_indexer_source"),
        CheckConstraint(
            "rate_limit_seconds >= 0", name="ck_indexer_rate_limit_nonneg"
        ),
        CheckConstraint(
            "priority BETWEEN 1 AND 100", name="ck_indexer_priority_range"
        ),
        CheckConstraint(
            "timeout_seconds BETWEEN 5 AND 120",
            name="ck_indexer_timeout_range",
        ),
        CheckConstraint(
            "result_limit BETWEEN 1 AND 500",
            name="ck_indexer_result_limit_range",
        ),
    )


class Application(Base):
    __tablename__ = "application"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sync_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="full_sync"
    )
    prowlarr_url: Mapped[str] = mapped_column(String, nullable=False)
    prowlarr_api_key_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    app_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("prowlarr_url", name="uq_application_prowlarr_url"),
        CheckConstraint(_SYNC_LEVEL_CHECK, name="ck_application_sync_level"),
    )


