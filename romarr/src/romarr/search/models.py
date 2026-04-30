"""SQLAlchemy models for the search subsystem.

Three new tables — ``blocklist``, ``search_history``,
``search_cache`` — plus the ``indexer.rss_auto_grab`` boolean
column added by the same migration.

Indexer FKs are nullable + ``ON DELETE SET NULL`` so deleting a
configured indexer doesn't wipe the audit history (FR-022).

The cache row carries ``response_xml`` (gzipped raw indexer body)
+ ``parsed_results`` (canonical SearchResult JSON projection); the
operator-tooling spec can replay an indexer response without
hitting the live service. RSS sync NEVER writes to ``search_cache``
(FR-027) — verified by tests in :mod:`tests.search.test_cache`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_SEARCH_TYPE_CHECK = (
    "search_type IN ('manual','auto_added','missing_scheduled',"
    "'cutoff_scheduled','rss')"
)


class Blocklist(Base):
    """Suppresses known-bad releases from being grabbed again."""

    __tablename__ = "blocklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indexer_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("indexer.id", ondelete="SET NULL"),
        nullable=True,
    )
    indexer_guid: Mapped[str | None] = mapped_column(String, nullable=True)
    release_title: Mapped[str] = mapped_column(String, nullable=False)
    hash_sha1: Mapped[str | None] = mapped_column(String(40), nullable=True)
    hash_crc32: Mapped[str | None] = mapped_column(String(8), nullable=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    added_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="system"
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("idx_blocklist_indexer_guid", "indexer_id", "indexer_guid"),
        Index("idx_blocklist_hash_sha1", "hash_sha1"),
        Index("idx_blocklist_hash_crc32", "hash_crc32"),
        Index("idx_blocklist_added_at", "added_at"),
    )


class SearchHistory(Base):
    """Audit trail of every search round (success or failure)."""

    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    search_type: Mapped[str] = mapped_column(String(32), nullable=False)
    query: Mapped[str | None] = mapped_column(String, nullable=True)
    indexer_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("indexer.id", ondelete="SET NULL"),
        nullable=True,
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
    results_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    grabbed_release_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("release.id", ondelete="SET NULL"),
        nullable=True,
    )
    chosen_indexer_guid: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    no_grab_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    score_breakdown: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON, nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)

    __table_args__ = (
        CheckConstraint(_SEARCH_TYPE_CHECK, name="ck_search_history_search_type"),
        Index("idx_search_history_started_at", "started_at"),
        Index("idx_search_history_game_started", "game_id", "started_at"),
        Index(
            "idx_search_history_type_started", "search_type", "started_at"
        ),
        Index("idx_search_history_correlation", "correlation_id"),
    )


class SearchCache(Base, TimestampMixin):
    """Caches indexer responses for non-RSS modes.

    ``cache_key`` is the SHA-256 hex of ``(query, frozenset(category_ids))``;
    UNIQUE per indexer so the same effective query can't double-cache.
    ``last_read_at`` powers the FR-028a LRU eviction (10 000 → 9 000
    rows on overflow).
    """

    __tablename__ = "search_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indexer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("indexer.id", ondelete="CASCADE"),
        nullable=False,
    )
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    query: Mapped[str] = mapped_column(String, nullable=False)
    category_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    response_xml: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    parsed_results: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "indexer_id", "cache_key", name="uq_search_cache_indexer_key"
        ),
        Index("idx_search_cache_expires_at", "expires_at"),
        Index("idx_search_cache_last_read_at", "last_read_at"),
    )


__all__ = ["Blocklist", "SearchCache", "SearchHistory"]
