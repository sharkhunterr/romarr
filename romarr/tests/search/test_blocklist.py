"""Blocklist helper tests (T035-T036)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers.models import Indexer
from romarr.indexers.types import SearchResult
from romarr.search.blocklist import (
    AUTO_BLOCKLIST_SUBREASONS,
    TRANSIENT_FAILURE_SUBREASONS,
    add_entry,
    auto_add_on_import_failure,
    delete_entry,
    is_auto_blocklist_subreason,
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
        reason="import-failed:dat-rejected",
    )
    assert row is not None
    assert row.reason == "import-failed:dat-rejected"


# ---------------------------------------------------------------------------
# CL010 — auto-blocklist taxonomy (FR-021 rewritten)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subreason",
    sorted(AUTO_BLOCKLIST_SUBREASONS),
)
@pytest.mark.asyncio
async def test_content_correctness_subreason_creates_blocklist_row(
    async_session: AsyncSession, subreason: str
) -> None:
    """Each content-correctness subreason MUST blocklist the
    release. These are the failure modes where the bytes
    themselves are wrong, so re-grabbing the same payload would
    fail again."""
    indexer = await _make_indexer(async_session)
    row = await auto_add_on_import_failure(
        async_session,
        result=_result(indexer_id=indexer.id, sha1="c" * 40),
        reason=subreason,
    )
    assert row is not None, f"{subreason} must blocklist"
    assert row.reason == f"import-failed:{subreason}"


@pytest.mark.parametrize(
    "subreason",
    sorted(TRANSIENT_FAILURE_SUBREASONS),
)
@pytest.mark.asyncio
async def test_transient_subreason_does_not_blocklist(
    async_session: AsyncSession, subreason: str
) -> None:
    """Each transient subreason MUST NOT blocklist. The next
    attempt could succeed against the same payload — disk
    space frees up, network heals, permissions get fixed."""
    indexer = await _make_indexer(async_session)
    row = await auto_add_on_import_failure(
        async_session,
        result=_result(indexer_id=indexer.id, sha1="d" * 40),
        reason=subreason,
    )
    assert row is None, f"{subreason} must NOT blocklist"

    # And the table is genuinely untouched.
    rows = (
        await async_session.execute(select(Blocklist))
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_unknown_subreason_does_not_blocklist(
    async_session: AsyncSession,
) -> None:
    """A subreason not in either set is fail-safe — no blocklist
    row. Better to miss an auto-blocklist than incorrectly
    suppress a release on a code we haven't classified yet."""
    indexer = await _make_indexer(async_session)
    row = await auto_add_on_import_failure(
        async_session,
        result=_result(indexer_id=indexer.id, sha1="e" * 40),
        reason="unknown-future-code",
    )
    assert row is None


@pytest.mark.asyncio
async def test_manual_add_works_for_any_subreason(
    async_session: AsyncSession,
) -> None:
    """The taxonomy gate only applies to ``auto_add_on_import_failure``.
    Manual ``add_entry`` calls (operator-driven) still work for
    any reason — the operator is the authority."""
    indexer = await _make_indexer(async_session)
    row = await add_entry(
        async_session,
        indexer_id=indexer.id,
        indexer_guid="manual-guid",
        release_title="Operator-added release",
        hash_sha1=None,
        hash_crc32=None,
        reason="operator decided this dump is wrong",
        added_by="operator-1",
    )
    assert row.id is not None


def test_auto_blocklist_taxonomy_is_disjoint() -> None:
    """The two sets must be disjoint — a code can't be both
    content-correctness AND transient. Catches a future
    reviewer accidentally adding the same code to both lists."""
    overlap = AUTO_BLOCKLIST_SUBREASONS & TRANSIENT_FAILURE_SUBREASONS
    assert overlap == frozenset()


def test_is_auto_blocklist_subreason_helper() -> None:
    """Helper accepts both bare codes and full prefixed strings."""
    assert is_auto_blocklist_subreason("hash-mismatch") is True
    assert is_auto_blocklist_subreason("import-failed:hash-mismatch") is True
    assert is_auto_blocklist_subreason("disk-full") is False
    assert is_auto_blocklist_subreason("import-failed:disk-full") is False
    assert is_auto_blocklist_subreason("totally-unknown") is False


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
