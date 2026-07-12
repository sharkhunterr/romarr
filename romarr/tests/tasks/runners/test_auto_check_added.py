"""Tests for the AutoCheckAddedRunner (spec 012 T052 + T048)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform
from romarr.tasks.runners.auto_check_added import run_search_on_add


@dataclass
class _FakeReport:
    """Minimal stand-in for ``SearchRoundReport`` — just the
    two list fields the runner counts."""

    candidates: list[object]
    grabs: list[object]


async def _seed_game(
    session: AsyncSession, *, title: str = "Sonic"
) -> Game:
    p = Platform(slug="md", name="MD")
    session.add(p)
    await session.flush()
    g = Game(platform_id=p.id, slug="sonic", title=title)
    session.add(g)
    await session.commit()
    return g


@pytest.mark.asyncio
async def test_run_search_on_add_searches_then_grabs(
    async_session: AsyncSession,
) -> None:
    """spec 012 T048 (test_event_driven, partial) — runner calls
    into the search round with the new Game's title + platform_id,
    then dispatches the winning candidate (on-add is an auto-grab
    path)."""
    game = await _seed_game(async_session, title="Sonic the Hedgehog")

    captured: dict[str, object] = {}

    async def _fake_search(session, query, platform_id):
        captured["query"] = query
        captured["platform_id"] = platform_id
        return _FakeReport(candidates=["c1", "c2", "c3"], grabs=[])

    async def _fake_dispatch(session, game_id, candidates):
        captured["dispatch_game_id"] = game_id
        captured["dispatch_candidates"] = list(candidates)
        return True

    result = await run_search_on_add(
        async_session,
        game_id=game.id,
        search_fn=_fake_search,
        dispatch_fn=_fake_dispatch,
    )

    assert captured["query"] == "Sonic the Hedgehog"
    assert captured["platform_id"] == game.platform_id
    # The runner re-derives + dispatches the winner from the round's
    # candidates — manual search itself never auto-grabs.
    assert captured["dispatch_game_id"] == game.id
    assert captured["dispatch_candidates"] == ["c1", "c2", "c3"]
    assert result.game_id == game.id
    assert result.title == "Sonic the Hedgehog"
    assert result.platform_id == game.platform_id
    assert result.candidates == 3
    assert result.grabs == 1
    assert result.skipped is False


@pytest.mark.asyncio
async def test_run_search_on_add_reports_zero_grabs_when_none_dispatched(
    async_session: AsyncSession,
) -> None:
    """Candidates found but none eligible to grab — runner reports
    candidates>0 with grabs=0 (no skip)."""
    game = await _seed_game(async_session)

    async def _fake_search(session, query, platform_id):
        return _FakeReport(candidates=["c1", "c2"], grabs=[])

    async def _fake_dispatch(session, game_id, candidates):
        return False

    result = await run_search_on_add(
        async_session,
        game_id=game.id,
        search_fn=_fake_search,
        dispatch_fn=_fake_dispatch,
    )

    assert result.candidates == 2
    assert result.grabs == 0
    assert result.skipped is False


@pytest.mark.asyncio
async def test_run_search_on_add_skips_when_game_missing(
    async_session: AsyncSession,
) -> None:
    """OnGameAdded fired for a Game that's already deleted —
    runner returns a structured skipped result rather than
    raising, and neither searches nor dispatches."""
    called = False
    dispatched = False

    async def _fake_search(session, query, platform_id):
        nonlocal called
        called = True
        return _FakeReport(candidates=[], grabs=[])

    async def _fake_dispatch(session, game_id, candidates):
        nonlocal dispatched
        dispatched = True
        return False

    result = await run_search_on_add(
        async_session,
        game_id=99999,
        search_fn=_fake_search,
        dispatch_fn=_fake_dispatch,
    )

    assert result.skipped is True
    assert result.skip_reason == "game_not_found"
    assert result.candidates == 0
    assert result.grabs == 0
    assert called is False
    assert dispatched is False


@pytest.mark.asyncio
async def test_run_search_on_add_handles_empty_round(
    async_session: AsyncSession,
) -> None:
    """No indexers configured / no results — round returns an
    empty report and the runner returns zero counts (no skip,
    nothing grabbed)."""
    game = await _seed_game(async_session)

    async def _fake_search(session, query, platform_id):
        return _FakeReport(candidates=[], grabs=[])

    async def _fake_dispatch(session, game_id, candidates):
        return False

    result = await run_search_on_add(
        async_session,
        game_id=game.id,
        search_fn=_fake_search,
        dispatch_fn=_fake_dispatch,
    )

    assert result.skipped is False
    assert result.candidates == 0
    assert result.grabs == 0
