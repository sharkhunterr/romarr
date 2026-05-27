"""Manual search round tests (T041-T042)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.indexers.errors import IndexerAuthError
from romarr.search.models import SearchHistory
from romarr.search.rounds.manual import (
    _manual_history_entries,
    run_manual_search,
)
from tests.search.rounds.conftest import (
    _FakeNewznabClient,
    make_search_result,
    seed_minimal_world,
)

# ---------------------------------------------------------------------------
# T041 — strict=true filters auto-rejected results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strict_filters_auto_rejected(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(async_session)
    indexer = indexers[0]

    results = [
        make_search_result(indexer_id=indexer.id, guid="match", title="Sonic the Hedgehog (USA)"),
        # No game match — pipeline rejects with NO_GAME_MATCH.
        make_search_result(indexer_id=indexer.id, guid="bad", title="Mortal Kombat ABCXYZ"),
    ]
    fake = _FakeNewznabClient(indexer_id=indexer.id, search_results=results)
    factory = fake_client_factory({indexer.id: fake})

    report = await run_manual_search(
        session=async_session,
        query="Sonic the Hedgehog",
        client_factory=factory,
        strict=True,
    )
    # Strict mode drops the rejected candidate.
    assert all(c.rejection is None for c in report.candidates)
    assert len(report.candidates) == 1
    assert report.candidates[0].indexer_guid == "match"


# ---------------------------------------------------------------------------
# T042 — default (strict=false) annotates with would_auto_reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_annotates_with_would_auto_reject(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(async_session)
    indexer = indexers[0]

    results = [
        make_search_result(indexer_id=indexer.id, guid="match", title="Sonic the Hedgehog (USA)"),
        make_search_result(indexer_id=indexer.id, guid="bad", title="Mortal Kombat ABCXYZ"),
    ]
    fake = _FakeNewznabClient(indexer_id=indexer.id, search_results=results)
    factory = fake_client_factory({indexer.id: fake})

    report = await run_manual_search(
        session=async_session,
        query="Sonic the Hedgehog",
        client_factory=factory,
        strict=False,
    )
    assert len(report.candidates) == 2
    rejected = [c for c in report.candidates if c.rejection is not None]
    accepted = [c for c in report.candidates if c.rejection is None]
    assert len(rejected) == 1
    assert rejected[0].would_auto_reject is True
    assert rejected[0].rejection is not None
    assert rejected[0].rejection.field == "title"
    assert len(accepted) == 1


# ---------------------------------------------------------------------------
# Multi-indexer fan-out + correlation_id sharing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_writes_one_history_row_per_indexer(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(async_session, indexer_count=3)
    fakes = {
        idx.id: _FakeNewznabClient(
            indexer_id=idx.id,
            search_results=[make_search_result(indexer_id=idx.id, guid=f"g-{idx.id}")],
        )
        for idx in indexers
    }
    factory = fake_client_factory(fakes)

    report = await run_manual_search(
        session=async_session,
        query="Sonic",
        client_factory=factory,
    )
    assert len(report.candidates) == 3
    rows = (await async_session.execute(select(SearchHistory))).scalars().all()
    assert len(rows) == 3
    assert {r.correlation_id for r in rows} == {str(report.correlation_id)}


# ---------------------------------------------------------------------------
# Indexer failure surfaces as "failed" outcome (no crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_indexer_auth_error_recorded_as_failed(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(async_session, indexer_count=2)
    fakes = {
        indexers[0].id: _FakeNewznabClient(
            indexer_id=indexers[0].id,
            raise_on_search=IndexerAuthError("bad creds"),
        ),
        indexers[1].id: _FakeNewznabClient(
            indexer_id=indexers[1].id,
            search_results=[
                make_search_result(indexer_id=indexers[1].id, guid="g")
            ],
        ),
    }
    factory = fake_client_factory(fakes)

    report = await run_manual_search(
        session=async_session,
        query="Sonic",
        client_factory=factory,
    )
    assert report.indexer_outcomes[indexers[0].id] == "failed"
    assert report.indexer_outcomes[indexers[1].id] == "ok"
    # Only the working indexer's result lands in candidates.
    assert len(report.candidates) == 1


# ---------------------------------------------------------------------------
# FR-029 hard cap — overcap indexer truncated, flagged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overcap_indexer_truncates_and_flags(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(async_session)
    indexer = indexers[0]
    flood = [
        make_search_result(indexer_id=indexer.id, guid=f"g{i}")
        for i in range(250)
    ]
    fake = _FakeNewznabClient(indexer_id=indexer.id, search_results=flood)
    factory = fake_client_factory({indexer.id: fake})

    report = await run_manual_search(
        session=async_session,
        query="Sonic",
        client_factory=factory,
    )
    # 200 hard cap (FR-029) — all 200 truncated entries make the report.
    assert len(report.candidates) == 200
    assert indexer.id in report.overcap_indexers


# ---------------------------------------------------------------------------
# indexer_ids filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_indexer_ids_filter_restricts_fan_out(
    async_session: AsyncSession,
    fake_client_factory: Callable[
        [dict[int, _FakeNewznabClient]],
        Callable[[int], Awaitable[_FakeNewznabClient]],
    ],
) -> None:
    indexers, _, _ = await seed_minimal_world(async_session, indexer_count=2)
    fakes = {
        idx.id: _FakeNewznabClient(
            indexer_id=idx.id,
            search_results=[make_search_result(indexer_id=idx.id, guid="g")],
        )
        for idx in indexers
    }
    factory = fake_client_factory(fakes)

    # Only indexer 0 selected.
    report = await run_manual_search(
        session=async_session,
        query="Sonic",
        client_factory=factory,
        indexer_ids=[indexers[0].id],
    )
    assert set(report.indexer_outcomes) == {indexers[0].id}
    # The unselected indexer's fake client wasn't asked.
    assert fakes[indexers[1].id].search_calls == []


# ---------------------------------------------------------------------------
# Unidentified-bucket history rows — torznab noise must not surface as a
# bogus failed "manual grab" in the History tab.
# ---------------------------------------------------------------------------


def test_manual_history_drops_unidentified_when_a_game_matched() -> None:
    """When at least one candidate matched a monitored game, the
    unidentified bucket (unrelated torznab results) is NOT recorded —
    it would otherwise render in History as a failed manual grab."""
    candidates = [
        SimpleNamespace(
            matched_game_id=7,
            rejection=None,
            score_breakdown=None,
            match_score=59,
            matched_release_id=None,
        ),
        SimpleNamespace(
            matched_game_id=None,
            rejection=None,
            score_breakdown=None,
            match_score=None,
            matched_release_id=None,
        ),
        SimpleNamespace(
            matched_game_id=None,
            rejection=None,
            score_breakdown=None,
            match_score=None,
            matched_release_id=None,
        ),
    ]

    entries = _manual_history_entries(
        indexer_id=1, indexer_candidates=candidates, outcome="ok"
    )

    game_ids = [e.get("game_id") for e in entries]
    assert 7 in game_ids
    assert None not in game_ids
    # The recorded score is the canonical match_score — the same
    # number the modal shows and the auto-grab floor gates on.
    matched = next(e for e in entries if e.get("game_id") == 7)
    assert matched["score"] == 59


def test_manual_history_keeps_unidentified_when_nothing_matched() -> None:
    """When NO candidate matched a monitored game, the unidentified
    row is kept — a genuine "found results but none usable" signal."""
    candidates = [
        SimpleNamespace(
            matched_game_id=None,
            rejection=None,
            score_breakdown=None,
            match_score=None,
            matched_release_id=None,
        ),
        SimpleNamespace(
            matched_game_id=None,
            rejection=None,
            score_breakdown=None,
            match_score=None,
            matched_release_id=None,
        ),
    ]

    entries = _manual_history_entries(
        indexer_id=1, indexer_candidates=candidates, outcome="ok"
    )

    assert len(entries) == 1
    assert entries[0]["game_id"] is None
    assert entries[0]["no_grab_reason"] == "unidentified"
    assert entries[0]["results_count"] == 2


def test_manual_history_scoped_to_requesting_game_emits_one_row() -> None:
    """When a manual search is initiated from a specific game's
    modal (``requesting_game_id`` set), the round emits ONE
    history row for that game — NOT one per fuzzy-matched
    library game.

    Without this scoping, the operator's Mario Hoops search from
    game 19's card would also populate games 17 (Mario & Luigi)
    and 18 (Mario & Sonic) with phantom "Manual search" rows
    that those games' History tabs would surface as searches the
    operator never ran for them."""
    # Indexer returned three candidates that GAMEMATCH fanned
    # out across three sibling games. Operator only wanted game 19.
    candidates = [
        SimpleNamespace(
            matched_game_id=19,
            matched_release_id=None,
            rejection=None,
            score_breakdown=None,
            match_score=56,
        ),
        SimpleNamespace(
            matched_game_id=17,  # sibling Mario game
            matched_release_id=None,
            rejection=None,
            score_breakdown=None,
            match_score=59,  # actually scores higher for sibling!
        ),
        SimpleNamespace(
            matched_game_id=18,  # sibling Mario game
            matched_release_id=None,
            rejection=None,
            score_breakdown=None,
            match_score=53,
        ),
    ]

    entries = _manual_history_entries(
        indexer_id=1,
        indexer_candidates=candidates,
        outcome="ok",
        requesting_game_id=19,
    )

    # Exactly one row, bound to the requesting game.
    assert len(entries) == 1
    assert entries[0]["game_id"] == 19
    # Uses the BEST overall score across all candidates as the
    # surfaced score — the operator wants to see the best Mario
    # Hoops-related hit, even if it was bound to a sibling game.
    assert entries[0]["score"] == 59
    assert entries[0]["results_count"] == 3
    assert entries[0]["no_grab_reason"] is None


def test_manual_history_scoped_returns_indexer_failure_with_game_id() -> None:
    """When the scoped search fails at the indexer level, the
    failure row still carries the ``requesting_game_id`` so the
    game's History tab surfaces "this game's search failed"
    rather than orphaning the row at game_id=None."""
    entries = _manual_history_entries(
        indexer_id=1,
        indexer_candidates=[],
        outcome="failed",
        requesting_game_id=42,
    )
    assert len(entries) == 1
    assert entries[0]["game_id"] == 42
    assert entries[0]["no_grab_reason"] == "indexer_failed"
