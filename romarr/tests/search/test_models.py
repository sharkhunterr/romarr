"""Search model + Pydantic-validator tests (T006-T008)."""

from __future__ import annotations

import gzip
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers.models import Indexer
from romarr.search.models import Blocklist, SearchCache, SearchHistory
from romarr.search.schemas import BlocklistCreate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_indexer(session: AsyncSession) -> Indexer:
    indexer = Indexer(
        name="Test Indexer",
        implementation="newznab",
        url="https://idx.test/api",
        categories=[1060],
        source="manual",
    )
    session.add(indexer)
    await session.commit()
    await session.refresh(indexer)
    return indexer


# ---------------------------------------------------------------------------
# T006 — round-trip + check constraints + unique constraint
# ---------------------------------------------------------------------------


async def test_blocklist_round_trip(async_session: AsyncSession) -> None:
    indexer = await _make_indexer(async_session)
    async_session.add(
        Blocklist(
            indexer_id=indexer.id,
            indexer_guid="guid-abc",
            release_title="Sonic.the.Hedgehog.[U].zip",
            hash_sha1="a" * 40,
            reason="import-failed:hash-mismatch",
            added_by="system",
            added_at=datetime.now(UTC),
        )
    )
    await async_session.commit()

    rows = (await async_session.execute(select(Blocklist))).scalars().all()
    assert len(rows) == 1
    assert rows[0].reason == "import-failed:hash-mismatch"


async def test_search_history_check_constraint(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        SearchHistory(
            search_type="not-a-real-type",
            results_count=0,
            started_at=datetime.now(UTC),
            correlation_id="corr-1",
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_search_history_round_trip(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        SearchHistory(
            search_type="manual",
            query="Sonic the Hedgehog",
            results_count=3,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            duration_ms=1234,
            correlation_id="corr-1",
        )
    )
    await async_session.commit()
    rows = (await async_session.execute(select(SearchHistory))).scalars().all()
    assert len(rows) == 1


async def test_search_cache_unique_indexer_key(
    async_session: AsyncSession,
) -> None:
    indexer = await _make_indexer(async_session)
    cache_key = hashlib.sha256(b"sonic|1060").hexdigest()
    now = datetime.now(UTC)
    async_session.add(
        SearchCache(
            indexer_id=indexer.id,
            cache_key=cache_key,
            query="sonic",
            category_ids=[1060],
            response_xml=gzip.compress(b"<rss/>"),
            parsed_results=[],
            fetched_at=now,
            expires_at=now + timedelta(hours=1),
            last_read_at=now,
        )
    )
    await async_session.commit()

    # Same (indexer_id, cache_key) → IntegrityError
    async_session.add(
        SearchCache(
            indexer_id=indexer.id,
            cache_key=cache_key,
            query="sonic",
            category_ids=[1060],
            response_xml=gzip.compress(b"<rss/>"),
            parsed_results=[],
            fetched_at=now,
            expires_at=now + timedelta(hours=1),
            last_read_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_indexer_rss_auto_grab_default_true(
    async_session: AsyncSession,
) -> None:
    """The new column defaults to true — indexers don't auto-block
    themselves from RSS auto-grab without an explicit operator opt-out."""
    indexer = await _make_indexer(async_session)
    assert indexer.rss_auto_grab is True


# ---------------------------------------------------------------------------
# T007 — Blocklist Pydantic validator: at least one match field
# ---------------------------------------------------------------------------


def test_blocklist_at_least_one_match_field_required() -> None:
    with pytest.raises(ValidationError, match="must carry one of"):
        BlocklistCreate(
            release_title="Some Release",
            reason="manual",
        )


def test_blocklist_with_only_indexer_id_no_guid_rejected() -> None:
    """indexer_id ALONE doesn't match anything — needs the GUID too."""
    with pytest.raises(ValidationError, match="must carry one of"):
        BlocklistCreate(
            indexer_id=1,
            release_title="Some Release",
            reason="manual",
        )


def test_blocklist_with_indexer_guid_pair_accepted() -> None:
    create = BlocklistCreate(
        indexer_id=1,
        indexer_guid="guid-1",
        release_title="x",
        reason="manual",
    )
    assert create.indexer_id == 1


def test_blocklist_with_hash_sha1_only_accepted() -> None:
    create = BlocklistCreate(
        release_title="x",
        hash_sha1="a" * 40,
        reason="manual",
    )
    assert create.hash_sha1 == "a" * 40


def test_blocklist_hash_sha1_length_validated() -> None:
    with pytest.raises(ValidationError):
        BlocklistCreate(
            release_title="x",
            hash_sha1="short",
            reason="manual",
        )


def test_blocklist_hash_crc32_only_accepted() -> None:
    create = BlocklistCreate(
        release_title="x",
        hash_crc32="DEADBEEF",
        reason="manual",
    )
    assert create.hash_crc32 == "DEADBEEF"
