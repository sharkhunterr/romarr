"""Tests for the on-add search round (spec 007 T056)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform
from romarr.search.rounds.on_add import run_search_on_add


@dataclass
class _FakeReport:
    candidates: list[object]
    grabs: list[object]


async def _seed_game(
    session: AsyncSession, *, title: str = "Sonic"
) -> Game:
    platform = Platform(slug="md", name="MD")
    session.add(platform)
    await session.flush()
    game = Game(
        platform_id=platform.id, slug=title.lower(), title=title
    )
    session.add(game)
    await session.commit()
    return game


@pytest.mark.asyncio
async def test_run_search_on_add_drives_one_round(
    async_session: AsyncSession,
) -> None:
    """Happy path: load Game, drive search, count outcomes."""
    game = await _seed_game(async_session, title="Sonic")

    captured: dict[str, object] = {}

    async def _fake_search(session, query, platform_id):
        captured["query"] = query
        captured["platform_id"] = platform_id
        return _FakeReport(candidates=["c1", "c2"], grabs=["g1"])

    result = await run_search_on_add(
        async_session, game_id=game.id, search_fn=_fake_search
    )
    assert captured["query"] == "Sonic"
    assert captured["platform_id"] == game.platform_id
    assert result.candidates == 2
    assert result.grabs == 1
    assert result.skipped is False


@pytest.mark.asyncio
async def test_run_search_on_add_best_effort_when_indexer_down(
    async_session: AsyncSession,
) -> None:
    """spec 007 T043 (test_best_effort_when_indexer_down) — a
    failed search MUST NOT raise; it returns ``skipped=True``
    so the API caller / scheduler dispatcher can record the
    failure without crashing."""
    game = await _seed_game(async_session)

    async def _flaky(session, query, platform_id):
        raise RuntimeError("all indexers unreachable")

    result = await run_search_on_add(
        async_session, game_id=game.id, search_fn=_flaky
    )
    assert result.skipped is True
    assert result.skip_reason == "RuntimeError"
    assert result.candidates == 0
    assert result.grabs == 0


@pytest.mark.asyncio
async def test_run_search_on_add_skips_missing_game(
    async_session: AsyncSession,
) -> None:
    called = False

    async def _fake_search(session, query, platform_id):
        nonlocal called
        called = True
        return _FakeReport(candidates=[], grabs=[])

    result = await run_search_on_add(
        async_session, game_id=99999, search_fn=_fake_search
    )
    assert result.skipped is True
    assert result.skip_reason == "game_not_found"
    assert called is False
