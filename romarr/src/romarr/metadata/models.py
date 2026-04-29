"""SQLAlchemy models for the metadata aggregation layer (spec 002).

Three new tables:

  - ``metadata_provider_config`` — per-provider toggle, credentials
    (encrypted), and rate-limit knobs.
  - ``metadata_cache`` — raw provider responses cached per (provider,
    Game). TTL-only eviction (FR-016a).
  - ``field_priority`` — the ranked, per-field provider preference list
    consumed by the aggregator.

The ``provider_name`` columns are TEXT with a CHECK against the closed
enumeration of nine known providers (see :data:`KNOWN_PROVIDERS`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BLOB,
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

KNOWN_PROVIDERS: tuple[str, ...] = (
    "igdb",
    "screenscraper",
    "mobygames",
    "launchbox",
    "steamgriddb",
    "retroachievements",
    "howlongtobeat",
    "hasheous",
    "playmatch",
)

_PROVIDER_CHECK_SQL = " IN (" + ",".join(f"'{p}'" for p in KNOWN_PROVIDERS) + ")"


class MetadataProviderConfig(Base, TimestampMixin):
    """Per-provider toggle + credentials.

    ``config_encrypted`` is a Fernet token wrapping a JSON object whose
    shape is provider-specific (e.g. ``{"client_id": "...", "client_secret": "..."}``
    for IGDB, ``{"username": "...", "password": "..."}`` for ScreenScraper).
    The encrypt/decrypt boundary lives in :mod:`romarr.metadata.encryption`.
    """

    __tablename__ = "metadata_provider_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_encrypted: Mapped[bytes | None] = mapped_column(BLOB, nullable=True)
    priority_global: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    cache_ttl_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2_592_000
    )
    rate_limit_rps: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    rate_limit_burst: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_check_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        UniqueConstraint("provider_name", name="uq_metadata_provider_config_name"),
        CheckConstraint(
            "provider_name" + _PROVIDER_CHECK_SQL,
            name="ck_metadata_provider_config_name",
        ),
    )


class MetadataCache(Base):
    """Per-(provider, Game) cached provider response.

    The unique constraint on ``(provider_name, provider_game_id)`` is
    the size-bounding mechanism (FR-016a): one row per provider/game.
    No LRU eviction; TTL only, via ``expires_at``.
    """

    __tablename__ = "metadata_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_game_id: Mapped[str] = mapped_column(String(128), nullable=False)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game.id", ondelete="CASCADE"),
        nullable=False,
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "provider_game_id",
            name="uq_metadata_cache_provider_game",
        ),
        Index("idx_metadata_cache_game_provider", "game_id", "provider_name"),
        Index("idx_metadata_cache_expires_at", "expires_at"),
        CheckConstraint(
            "provider_name" + _PROVIDER_CHECK_SQL,
            name="ck_metadata_cache_provider_name",
        ),
    )


class FieldPriority(Base):
    """Per-(field, provider) rank within the field.

    Aggregator consumes rows ordered by ``priority_order`` ASC, picks
    the first provider with a non-empty value, and skips locked fields.
    The composite UNIQUE on (field, priority_order) prevents two
    providers from claiming the same rank within a field.
    """

    __tablename__ = "field_priority"

    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    priority_order: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "field_name", "provider_name", name="pk_field_priority"
        ),
        UniqueConstraint(
            "field_name",
            "priority_order",
            name="uq_field_priority_field_order",
        ),
        CheckConstraint(
            "provider_name" + _PROVIDER_CHECK_SQL,
            name="ck_field_priority_provider_name",
        ),
    )
