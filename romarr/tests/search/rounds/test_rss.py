"""RSS sync round tests (T053 / FR-027 / US7)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.search.models import SearchHistory
from romarr.search.rounds.rss import run_rss_sync
from tests.search.rounds.conftest import (
    _FakeNewznabClient,
    make_search_result,
    seed_minimal_world,
)

# ---------------------------------------------------------------------------
# Happy path — RSS round writes one history row + populates grabs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rss_round_writes_history_and_grabs(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(async_session)
    indexer = indexers[0]
    rss_results = [
        make_search_result(
            indexer_id=indexer.id,
            guid="rss-1",
            title="Sonic the Hedgehog (USA)",
            region="USA",
        )
    ]
    fake = _FakeNewznabClient(indexer_id=indexer.id, rss_results=rss_results)
    factory = fake_client_factory({indexer.id: fake})

    report = await run_rss_sync(
        session=async_session, client_factory=factory
    )
    assert report.search_type == "rss"
    assert report.indexer_outcomes[indexer.id] == "ok"
    assert fake.rss_calls == 1
    rows = (await async_session.execute(select(SearchHistory))).scalars().all()
    assert len(rows) == 1
    assert rows[0].search_type == "rss"
    assert rows[0].query is None  # RSS rows carry no query


# ---------------------------------------------------------------------------
# US7 / FR-027 — rss_auto_grab=false records but doesn't grab
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rss_auto_grab_false_records_but_does_not_grab(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(
        async_session, rss_auto_grab=False
    )
    indexer = indexers[0]
    rss_results = [
        make_search_result(
            indexer_id=indexer.id, guid="x", region="USA", title="Sonic the Hedgehog (USA)"
        )
    ]
    fake = _FakeNewznabClient(indexer_id=indexer.id, rss_results=rss_results)
    factory = fake_client_factory({indexer.id: fake})

    report = await run_rss_sync(
        session=async_session, client_factory=factory
    )
    assert len(report.candidates) == 1  # recorded
    assert report.grabs == []  # but never auto-grabbed


# ---------------------------------------------------------------------------
# enable_rss=false indexers are skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rss_skips_indexers_with_enable_rss_false(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(async_session, enable_rss=False)
    fakes = {
        idx.id: _FakeNewznabClient(indexer_id=idx.id) for idx in indexers
    }
    factory = fake_client_factory(fakes)

    report = await run_rss_sync(
        session=async_session, client_factory=factory
    )
    assert report.indexer_outcomes == {}
    # No fake's rss() was called.
    for fake in fakes.values():
        assert fake.rss_calls == 0


# ---------------------------------------------------------------------------
# Score = 0 candidates aren't auto-grabbed even when rss_auto_grab=true
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_score_not_grabbed_even_with_auto_grab_true(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    """A candidate with score = 0 (fallback region, no custom format
    bonus) is recorded but not auto-grabbed — RSS only fires on a
    positive-score signal."""
    indexers, _, _ = await seed_minimal_world(async_session)
    indexer = indexers[0]
    # BRA region falls outside priorities; fallback gives score=0.
    rss_results = [
        make_search_result(
            indexer_id=indexer.id, guid="g", region="BRA", title="Sonic the Hedgehog (BRA)"
        )
    ]
    fake = _FakeNewznabClient(indexer_id=indexer.id, rss_results=rss_results)
    factory = fake_client_factory({indexer.id: fake})

    report = await run_rss_sync(
        session=async_session, client_factory=factory
    )
    assert len(report.candidates) == 1
    # Score is 0 → no grab.
    assert report.grabs == []
