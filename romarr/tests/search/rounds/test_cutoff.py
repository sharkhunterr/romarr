"""Tests for the cutoff-search round (spec 007 T058)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform, Release
from romarr.search.rounds.cutoff import (
    DEFAULT_LIMIT,
    run_cutoff_search,
)


@dataclass
class _FakeReport:
    candidates: list[object]
    grabs: list[object]


async def _seed_release(
    session: AsyncSession,
    *,
    title: str,
    status: str = "imported",
    monitored: bool = True,
    cutoff_met: bool = False,
) -> Release:
    platform = (
        await session.execute(
            __import__("sqlalchemy").select(Platform).where(Platform.slug == "md")
        )
    ).scalar_one_or_none()
    if platform is None:
        platform = Platform(slug="md", name="MD")
        session.add(platform)
        await session.flush()
    game = Game(platform_id=platform.id, slug=title.lower(), title=title)
    session.add(game)
    await session.flush()
    release = Release(
        game_id=game.id,
        name=f"{title} (USA)",
        status=status,
        monitored=monitored,
        cutoff_met=cutoff_met,
    )
    session.add(release)
    await session.commit()
    return release


def test_default_limit_is_50() -> None:
    assert DEFAULT_LIMIT == 50


@pytest.mark.asyncio
async def test_run_cutoff_search_iterates_below_cutoff(
    async_session: AsyncSession,
) -> None:
    """Imported + below-cutoff + monitored → probed."""
    await _seed_release(async_session, title="Sonic")
    await _seed_release(async_session, title="Mario")

    async def _fake_search(session, query, platform_id):
        return _FakeReport(candidates=["c"], grabs=[])

    result = await run_cutoff_search(
        async_session, search_fn=_fake_search
    )
    assert result.total == 2
    assert result.succeeded == 2


@pytest.mark.asyncio
async def test_run_cutoff_search_skips_at_cutoff(
    async_session: AsyncSession,
) -> None:
    """``cutoff_met=true`` → quality satisfied, no upgrade probe."""
    await _seed_release(
        async_session, title="Sonic", cutoff_met=True
    )
    await _seed_release(
        async_session, title="Mario", cutoff_met=False
    )

    visited: list[str] = []

    async def _fake_search(session, query, platform_id):
        visited.append(query)
        return _FakeReport(candidates=[], grabs=[])

    result = await run_cutoff_search(
        async_session, search_fn=_fake_search
    )
    assert result.total == 1
    assert visited == ["Mario"]


@pytest.mark.asyncio
async def test_run_cutoff_search_skips_wanted(
    async_session: AsyncSession,
) -> None:
    """Wanted Releases (no Dump yet) belong to the missing-search
    round, not cutoff-search."""
    await _seed_release(async_session, title="Sonic", status="wanted")
    await _seed_release(async_session, title="Mario", status="imported")

    async def _fake_search(session, query, platform_id):
        return _FakeReport(candidates=[], grabs=[])

    result = await run_cutoff_search(
        async_session, search_fn=_fake_search
    )
    assert result.total == 1


@pytest.mark.asyncio
async def test_run_cutoff_search_skips_unmonitored(
    async_session: AsyncSession,
) -> None:
    await _seed_release(
        async_session, title="Sonic", monitored=False
    )
    await _seed_release(async_session, title="Mario")

    async def _fake_search(session, query, platform_id):
        return _FakeReport(candidates=[], grabs=[])

    result = await run_cutoff_search(
        async_session, search_fn=_fake_search
    )
    assert result.total == 1


@pytest.mark.asyncio
async def test_run_cutoff_search_per_release_failure_does_not_abort(
    async_session: AsyncSession,
) -> None:
    r1 = await _seed_release(async_session, title="Sonic")
    await _seed_release(async_session, title="Mario")

    async def _flaky(session, query, platform_id):
        if query == "Sonic":
            raise RuntimeError("provider 503")
        return _FakeReport(candidates=["c"], grabs=[])

    result = await run_cutoff_search(
        async_session, search_fn=_flaky
    )
    assert result.total == 2
    assert result.succeeded == 1
    skipped = [o for o in result.outcomes if o.skipped]
    assert len(skipped) == 1
    assert skipped[0].release_id == r1.id


@pytest.mark.asyncio
async def test_run_cutoff_search_respects_limit(
    async_session: AsyncSession,
) -> None:
    for title in ("Q1", "Q2", "Q3", "Q4"):
        await _seed_release(async_session, title=title)

    async def _fake_search(session, query, platform_id):
        return _FakeReport(candidates=[], grabs=[])

    result = await run_cutoff_search(
        async_session, limit=2, search_fn=_fake_search
    )
    assert result.total == 2
