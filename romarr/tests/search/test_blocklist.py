"""Blocklist helper tests (T035-T036)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers.models import Indexer
from romarr.indexers.types import SearchResult
from romarr.search.blocklist import (
    add_entry,
    auto_add_on_import_failure,
    delete_entry,
    is_blocklisted,
)
from romarr.search.models import Blocklist


def _result(
    *,
    guid: str = "guid-1",
    indexer_id: int = 1,
    title: str = "Sonic the Hedgehog (USA)",
    sha1: str | None = None,
    crc: str | None = None,
) -> SearchResult:
    return SearchResult(
        indexer_id=indexer_id,
        guid=guid,
        title=title,
        link=f"https://idx.test/{guid}",
        hash_sha1=sha1,
        hash_crc32=crc,
    )


async def _make_indexer(session: AsyncSession) -> Indexer:
    indexer = Indexer(
        name="Test",
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
# T035 — auto-add on import failure (FR-021)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_add_on_import_failure(async_session: AsyncSession) -> None:
    indexer = await _make_indexer(async_session)
    row = await auto_add_on_import_failure(
        async_session,
        result=_result(indexer_id=indexer.id, sha1="a" * 40),
        reason="hash-mismatch",
    )
    assert row.added_by == "system"
    assert row.reason == "import-failed:hash-mismatch"
    assert row.hash_sha1 == "a" * 40
    assert row.indexer_id == indexer.id


@pytest.mark.asyncio
async def test_auto_add_does_not_double_prefix(
    async_session: AsyncSession,
) -> None:
    """A reason already prefixed with import-failed: stays as-is."""
    indexer = await _make_indexer(async_session)
    row = await auto_add_on_import_failure(
        async_session,
        result=_result(indexer_id=indexer.id, sha1="b" * 40),
        reason="import-failed:custom",
    )
    assert row.reason == "import-failed:custom"


# ---------------------------------------------------------------------------
# T036 — lookup by guid / sha1 / crc32 (table-driven)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_by_guid(async_session: AsyncSession) -> None:
    indexer = await _make_indexer(async_session)
    await add_entry(
        async_session,
        indexer_id=indexer.id,
        indexer_guid="bad",
        release_title="Bad release",
        reason="manual",
    )
    hit = await is_blocklisted(
        async_session, result=_result(indexer_id=indexer.id, guid="bad")
    )
    assert hit is not None
    assert hit.indexer_guid == "bad"


@pytest.mark.asyncio
async def test_lookup_by_sha1(async_session: AsyncSession) -> None:
    sha = "a" * 40
    await add_entry(
        async_session,
        release_title="Bad",
        reason="manual",
        hash_sha1=sha,
    )
    hit = await is_blocklisted(async_session, result=_result(sha1=sha))
    assert hit is not None
    assert hit.hash_sha1 == sha


@pytest.mark.asyncio
async def test_lookup_by_crc32(async_session: AsyncSession) -> None:
    crc = "DEADBEEF"
    await add_entry(
        async_session,
        release_title="Bad",
        reason="manual",
        hash_crc32=crc,
    )
    hit = await is_blocklisted(async_session, result=_result(crc=crc))
    assert hit is not None
    assert hit.hash_crc32 == crc.lower()  # stored lowercase


@pytest.mark.asyncio
async def test_lookup_no_match_returns_none(
    async_session: AsyncSession,
) -> None:
    hit = await is_blocklisted(
        async_session, result=_result(guid="never-blocked")
    )
    assert hit is None


# ---------------------------------------------------------------------------
# delete_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_entry(async_session: AsyncSession) -> None:
    indexer = await _make_indexer(async_session)
    row = await add_entry(
        async_session,
        indexer_id=indexer.id,
        indexer_guid="x",
        release_title="X",
        reason="manual",
    )
    deleted = await delete_entry(async_session, entry_id=row.id)
    assert deleted is True
    rows = (await async_session.execute(select(Blocklist))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_delete_entry_missing_returns_false(
    async_session: AsyncSession,
) -> None:
    deleted = await delete_entry(async_session, entry_id=9999)
    assert deleted is False
