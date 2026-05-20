"""SQLAlchemy models for the REST API & WebSocket feature (spec 013).

Three tables added in migration ``0013_rest_api``:

  * :class:`Tag` — global, polymorphic tag definitions. Each row is
    a (name, color, label) tuple. Tags attach to any tagged entity
    via :class:`TagAssignment` rather than per-entity FKs so the
    Tag UI can target Game / Indexer / Notification / Release
    uniformly. Deleting a Tag cascades to assignments via FK
    ``ON DELETE CASCADE``; deleting an entity cleans up via the
    application-level cleanup hook (no FK on ``entity_id`` is
    possible because it spans tables).
  * :class:`QueueEntry` — Romarr's mirror of the download client's
    queue. Spec 005 writes new entries on grab; spec 008's import
    pipeline reads them; the ``/api/v3/queue`` endpoint exposes
    them. The unique ``(download_client_id,
    download_client_native_id)`` index lets the reconciler upsert
    in one call.
  * :class:`IdempotencyCache` — DB fallback for the FR-020/FR-025
    Idempotency-Key cache. Redis is the primary backend; this
    table is the rope-bridge for deployments without Redis.
    Composite PK ``(endpoint, key)`` ensures the same key reused
    on a different endpoint is treated as a fresh request, which
    matches RFC draft semantics.

The brand-default ``tag.color`` is the Game Boy LCD green
``#9BBC0F`` clarified in spec 014.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin


def _utcnow() -> datetime:
    return datetime.now(UTC)


# Brand-default Tag colour — Game Boy LCD green (spec 014).
DEFAULT_TAG_COLOR = "#9BBC0F"

_TAG_ENTITY_TYPE_CHECK = (
    "entity_type IN ('game', 'indexer', 'notification', 'release')"
)
_QUEUE_STATE_CHECK = (
    "state IN ("
    "'queued', 'downloading', 'paused', 'completed', "
    "'stuck', 'failed', 'pending_retry', "
    # Slice 478 — ROM-pack ingest phases mirrored into the queue
    # so the operator watches the post-download work the same way
    # they watch a download.
    "'extracting', 'importing'"
    ")"
)


class Tag(Base, TimestampMixin):
    """Operator-defined tag. Applied across multiple entity types
    via :class:`TagAssignment` rows."""

    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    color: Mapped[str] = mapped_column(
        String, nullable=False, default=DEFAULT_TAG_COLOR
    )
    label: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("idx_tag_name", "name"),)


class TagAssignment(Base):
    """Polymorphic m2m linking a :class:`Tag` to any entity row.

    No FK on ``entity_id`` because the target table varies.
    Per-entity ``before_delete`` hooks in the application layer
    are responsible for sweeping orphaned assignments — see the
    data-model.md cross-spec consistency notes.
    """

    __tablename__ = "tag_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tag.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "tag_id",
            "entity_type",
            "entity_id",
            name="uq_tag_assignment_unique",
        ),
        CheckConstraint(
            _TAG_ENTITY_TYPE_CHECK, name="ck_tag_assignment_entity_type"
        ),
        Index(
            "idx_tag_assignment_lookup",
            "entity_type",
            "entity_id",
        ),
        Index("idx_tag_assignment_tag", "tag_id"),
    )


class QueueEntry(Base):
    """One row mirrors one entry in a download client's queue.

    The reconciler upserts on the
    ``(download_client_id, download_client_native_id)`` unique key
    — that pair is the operator-facing identity (info-hash for
    qBit, ``nzo_id`` for SAB).
    """

    __tablename__ = "queue_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    release_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("release.id", ondelete="CASCADE"),
        nullable=True,
    )
    # Slice 367: operator-readable title (torrent / NZB name)
    # and the parent game's id so the Activity → Queue tab can
    # show "Mario Kart · Super Circuit (USA).gba" instead of the
    # bare info-hash.
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    game_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("game.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Nullable since slice 465 — a Romarr-internal download (a
    # URL-sourced ROM content pack Romarr streams itself) has no
    # originating download client. The reconciler skips
    # NULL-client rows; the ROM-pack ingest pipeline drives their
    # progress instead.
    download_client_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("download_client.id", ondelete="CASCADE"),
        nullable=True,
    )
    download_client_native_id: Mapped[str] = mapped_column(
        String, nullable=False
    )
    state: Mapped[str] = mapped_column(String, nullable=False)
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    eta_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    error_msg: Mapped[str | None] = mapped_column(String, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Slice 454 — durable "where did the finished file land" +
    # "did we already hand it to run_import" so a completed
    # download survives a container restart. The grabarr-direct
    # client's in-memory ``_pending`` dict doesn't; without these
    # the watcher loses the import trigger on restart.
    content_path: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    import_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "download_client_id",
            "download_client_native_id",
            name="uq_queue_entry_native_id",
        ),
        CheckConstraint(_QUEUE_STATE_CHECK, name="ck_queue_entry_state"),
        Index("idx_queue_entry_release", "release_id"),
        Index("idx_queue_entry_state", "state"),
    )


class IdempotencyCache(Base):
    """DB fallback for the Idempotency-Key cache (FR-020 / FR-025).

    The PK is composite ``(endpoint, key)`` so the same key reused
    on a different endpoint is a separate cache slot — matches the
    RFC draft semantics and prevents cross-endpoint leakage.

    ``request_body_hash`` is the hex of
    ``SHA-256(JCS-canonical-JSON(body))`` per RFC 8785 for JSON
    bodies; multipart and binary bodies fall back to plain
    ``SHA-256(raw bytes)``. Replays whose body hash differs from
    the stored value MUST surface HTTP 422 with reason
    ``idempotency_key_body_mismatch``.
    """

    __tablename__ = "idempotency_cache"

    endpoint: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_body_hash: Mapped[str] = mapped_column(String, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    response_headers: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("idx_idempotency_cache_expires_at", "expires_at"),
    )


__all__ = [
    "DEFAULT_TAG_COLOR",
    "IdempotencyCache",
    "QueueEntry",
    "Tag",
    "TagAssignment",
]
