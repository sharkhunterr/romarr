"""Tests for the RefreshAllMetadataRunner (spec 012 T050)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform
from romarr.tasks.runners.refresh_all_metadata import (
    refresh_all_metadata,
)


async def _seed_platform(
    session: AsyncSession, *, slug: str = "megadrive"
) -> Platform:
    p = Platform(slug=slug, name=slug.upper())
    session.add(p)
    await session.flush()
    return p


async def _seed_games(
    session: AsyncSession, *, platform: Platform, count: int
) -> list[int]:
    ids: list[int] = []
    for i in range(count):
        g = Game(
            platform_id=platform.id,
            slug=f"{platform.slug}-{i}",
            title=f"Game {i}",
        )
        session.add(g)
        await session.flush()
        ids.append(g.id)
    await session.commit()
    return ids


@pytest.mark.asyncio
async def test_paginated_visits_every_game(
    async_session: AsyncSession,
) -> None:
    """spec 012 T046 (test_paginated) — the sweep visits every
    Game exactly once across multiple pages."""
    p = await _seed_platform(async_session)
    seeded_ids = await _seed_games(async_session, platform=p, count=250)

    visited: list[int] = []

    async def _fake_refresh(session, *, game_id, force):
        visited.append(game_id)

    result = await refresh_all_metadata(
        async_session,
        page_size=50,  # forces 5 round trips
        refresh_fn=_fake_refresh,
    )
    assert result.total == 250
    assert result.refreshed == 250
    assert result.failed == 0
    assert sorted(visited) == sorted(seeded_ids)


@pytest.mark.asyncio
async def test_per_game_failure_is_counted_not_fatal(
    async_session: AsyncSession,
) -> None:
    """A single provider failure must not kill the sweep."""
    p = await _seed_platform(async_session)
    ids = await _seed_games(async_session, platform=p, count=5)

    async def _flaky(session, *, game_id, force):
        if game_id == ids[2]:
            raise RuntimeError("provider down")

    result = await refresh_all_metadata(
        async_session, refresh_fn=_flaky
    )
    assert result.total == 5
    assert result.refreshed == 4
    assert result.failed == 1


@pytest.mark.asyncio
async def test_platform_id_scopes_the_sweep(
    async_session: AsyncSession,
) -> None:
    """``platform_id`` restricts the sweep to one Platform."""
    md = await _seed_platform(async_session, slug="md")
    snes = await _seed_platform(async_session, slug="snes")
    md_ids = await _seed_games(async_session, platform=md, count=3)
    await _seed_games(async_session, platform=snes, count=4)

    visited: list[int] = []

    async def _fake_refresh(session, *, game_id, force):
        visited.append(game_id)

    result = await refresh_all_metadata(
        async_session,
        platform_id=md.id,
        refresh_fn=_fake_refresh,
    )
    assert result.total == 3
    assert sorted(visited) == sorted(md_ids)


@pytest.mark.asyncio
async def test_empty_library_returns_zero_counts(
    async_session: AsyncSession,
) -> None:
    """Empty Game table — sweep returns zero counts cleanly."""

    async def _fake_refresh(session, *, game_id, force):
        raise AssertionError("should never be called")

    result = await refresh_all_metadata(
        async_session, refresh_fn=_fake_refresh
    )
    assert result.total == 0
    assert result.refreshed == 0
    assert result.failed == 0
    assert result.last_game_id is None


@pytest.mark.asyncio
async def test_force_flag_propagates_through(
    async_session: AsyncSession,
) -> None:
    """The ``force`` flag is forwarded to the refresh fn."""
    p = await _seed_platform(async_session)
    await _seed_games(async_session, platform=p, count=2)

    seen_force: list[bool] = []

    async def _capture(session, *, game_id, force):
        seen_force.append(force)

    await refresh_all_metadata(
        async_session, force=True, refresh_fn=_capture
    )
    assert seen_force == [True, True]
