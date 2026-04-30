"""Search-history audit helper tests (T037)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers.models import Indexer
from romarr.search.history import record_round
from romarr.search.models import SearchHistory


async def _make_indexer(session: AsyncSession, *, name: str) -> Indexer:
    indexer = Indexer(
        name=name,
        implementation="newznab",
        url=f"https://{name}.test/api",
        categories=[1060],
        source="manual",
    )
    session.add(indexer)
    await session.commit()
    await session.refresh(indexer)
    return indexer


# ---------------------------------------------------------------------------
# T037 — one row per indexer in a round; shared correlation_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_creates_one_row_per_indexer(
    async_session: AsyncSession,
) -> None:
    a = await _make_indexer(async_session, name="ndx-a")
    b = await _make_indexer(async_session, name="ndx-b")
    c = await _make_indexer(async_session, name="ndx-c")

    correlation_id = str(uuid.uuid4())
    rows = await record_round(
        async_session,
        correlation_id=correlation_id,
        search_type="manual",
        query="Sonic the Hedgehog",
        indexer_results=[
            {"indexer_id": a.id, "results_count": 5},
            {"indexer_id": b.id, "results_count": 12},
            {"indexer_id": c.id, "results_count": 0, "no_grab_reason": "no_results"},
        ],
    )
    assert len(rows) == 3
    assert {r.correlation_id for r in rows} == {correlation_id}
    assert {r.indexer_id for r in rows} == {a.id, b.id, c.id}

    # The third row carries the documented no_grab_reason.
    no_grab = next(r for r in rows if r.no_grab_reason)
    assert no_grab.no_grab_reason == "no_results"


@pytest.mark.asyncio
async def test_record_round_persists_score_breakdown(
    async_session: AsyncSession,
) -> None:
    indexer = await _make_indexer(async_session, name="ndx-a")
    correlation_id = str(uuid.uuid4())
    await record_round(
        async_session,
        correlation_id=correlation_id,
        search_type="missing_scheduled",
        query=None,
        indexer_results=[
            {
                "indexer_id": indexer.id,
                "results_count": 4,
                "score": 113,
                "score_breakdown": [
                    {"source": "region", "name": "USA First", "value": 3},
                    {"source": "custom_format", "name": "Verified", "value": 100},
                    {"source": "custom_format", "name": "No-Intro", "value": 10},
                ],
            }
        ],
    )

    persisted = (
        (await async_session.execute(select(SearchHistory))).scalars().all()
    )
    assert len(persisted) == 1
    assert persisted[0].score == 113
    assert persisted[0].search_type == "missing_scheduled"
    assert persisted[0].query is None
    assert persisted[0].score_breakdown is not None
    assert len(persisted[0].score_breakdown) == 3


@pytest.mark.asyncio
async def test_record_round_with_explicit_timestamps(
    async_session: AsyncSession,
) -> None:
    indexer = await _make_indexer(async_session, name="ndx-a")
    started = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 4, 1, 12, 0, 5, tzinfo=UTC)
    rows = await record_round(
        async_session,
        correlation_id="corr-1",
        search_type="manual",
        query="x",
        indexer_results=[
            {
                "indexer_id": indexer.id,
                "results_count": 1,
                "started_at": started,
                "finished_at": finished,
                "duration_ms": 5000,
            }
        ],
    )
    assert rows[0].duration_ms == 5000
