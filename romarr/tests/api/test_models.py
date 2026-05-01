"""Spec 013 model round-trip tests (T003).

Covers the three new tables shipped in migration ``0013_rest_api``:

  * :class:`Tag` — name uniqueness, default colour, label
    persistence.
  * :class:`TagAssignment` — entity_type CHECK constraint,
    composite-uniqueness, FK CASCADE on tag delete.
  * :class:`QueueEntry` — state CHECK constraint, native-id
    uniqueness within a download client.
  * :class:`IdempotencyCache` — composite PK (``endpoint`` +
    ``key``); same key on a different endpoint persists as a
    separate row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.models import (
    DEFAULT_TAG_COLOR,
    IdempotencyCache,
    QueueEntry,
    Tag,
    TagAssignment,
)

# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_round_trip(async_session: AsyncSession) -> None:
    tag = Tag(name="family-friendly", label="Family Friendly")
    async_session.add(tag)
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(Tag).where(Tag.name == "family-friendly")
        )
    ).scalar_one()
    assert fetched.label == "Family Friendly"
    assert fetched.color == DEFAULT_TAG_COLOR


@pytest.mark.asyncio
async def test_tag_name_is_unique(async_session: AsyncSession) -> None:
    async_session.add(Tag(name="dup", label="A"))
    await async_session.commit()

    async_session.add(Tag(name="dup", label="B"))
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# TagAssignment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_assignment_round_trip(
    async_session: AsyncSession,
) -> None:
    tag = Tag(name="hidden-gem", label="Hidden Gem")
    async_session.add(tag)
    await async_session.commit()

    async_session.add(
        TagAssignment(
            tag_id=tag.id,
            entity_type="game",
            entity_id=42,
        )
    )
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(TagAssignment).where(TagAssignment.tag_id == tag.id)
        )
    ).scalar_one()
    assert fetched.entity_type == "game"
    assert fetched.entity_id == 42


@pytest.mark.asyncio
async def test_tag_assignment_invalid_entity_type_rejected(
    async_session: AsyncSession,
) -> None:
    tag = Tag(name="bad-type", label="Bad")
    async_session.add(tag)
    await async_session.commit()

    async_session.add(
        TagAssignment(
            tag_id=tag.id,
            entity_type="not-a-real-type",
            entity_id=1,
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_tag_assignment_unique_composite(
    async_session: AsyncSession,
) -> None:
    tag = Tag(name="uniq", label="Uniq")
    async_session.add(tag)
    await async_session.commit()

    async_session.add(
        TagAssignment(tag_id=tag.id, entity_type="game", entity_id=1)
    )
    await async_session.commit()

    async_session.add(
        TagAssignment(tag_id=tag.id, entity_type="game", entity_id=1)
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_tag_delete_cascades_to_assignments(
    async_session: AsyncSession,
) -> None:
    tag = Tag(name="cascade-me", label="Cascade")
    async_session.add(tag)
    await async_session.commit()

    async_session.add(
        TagAssignment(tag_id=tag.id, entity_type="release", entity_id=7)
    )
    await async_session.commit()

    await async_session.delete(tag)
    await async_session.commit()

    rows = (
        await async_session.execute(
            select(TagAssignment).where(TagAssignment.tag_id == tag.id)
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# QueueEntry — note: requires real release + download_client rows for FKs,
# which would couple this test to the broader fixtures; instead we exercise
# the table's CHECK / UNIQUE invariants without inserting FK targets, by
# disabling FKs on the in-memory session for this single test.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_entry_state_check(
    async_session: AsyncSession,
) -> None:
    """``state`` is constrained to the documented set."""
    # Disable FKs for this single check — we're testing the CHECK
    # constraint, not the FK.
    await async_session.execute(text("PRAGMA foreign_keys=OFF"))
    bad = QueueEntry(
        release_id=1,
        download_client_id=1,
        download_client_native_id="abc",
        state="weird",
    )
    async_session.add(bad)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_queue_entry_native_id_unique_per_client(
    async_session: AsyncSession,
) -> None:
    """``(download_client_id, download_client_native_id)`` is the
    operator-facing identity — duplicates collapse on UPSERT."""
    await async_session.execute(text("PRAGMA foreign_keys=OFF"))

    async_session.add(
        QueueEntry(
            release_id=1,
            download_client_id=1,
            download_client_native_id="hash-abc",
            state="queued",
        )
    )
    await async_session.commit()

    async_session.add(
        QueueEntry(
            release_id=2,
            download_client_id=1,
            download_client_native_id="hash-abc",
            state="downloading",
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# IdempotencyCache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_cache_round_trip(
    async_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    row = IdempotencyCache(
        endpoint="POST /api/v3/rom/release/grab",
        key="xyz-123",
        request_body_hash="deadbeef",
        response_status=202,
        response_body=b"{}",
        expires_at=now + timedelta(hours=24),
    )
    async_session.add(row)
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(IdempotencyCache).where(
                IdempotencyCache.key == "xyz-123"
            )
        )
    ).scalar_one()
    assert fetched.response_status == 202
    assert fetched.response_body == b"{}"
    assert fetched.response_headers == {}


@pytest.mark.asyncio
async def test_idempotency_cache_pk_composite(
    async_session: AsyncSession,
) -> None:
    """The same key on a different endpoint is a separate row."""
    now = datetime.now(UTC)
    async_session.add_all(
        [
            IdempotencyCache(
                endpoint="POST /a",
                key="shared-key",
                request_body_hash="h1",
                response_status=200,
                response_body=b"{}",
                expires_at=now + timedelta(hours=1),
            ),
            IdempotencyCache(
                endpoint="POST /b",
                key="shared-key",
                request_body_hash="h2",
                response_status=200,
                response_body=b"{}",
                expires_at=now + timedelta(hours=1),
            ),
        ]
    )
    await async_session.commit()

    rows = (
        await async_session.execute(
            select(IdempotencyCache).where(
                IdempotencyCache.key == "shared-key"
            )
        )
    ).scalars().all()
    assert {row.endpoint for row in rows} == {"POST /a", "POST /b"}
