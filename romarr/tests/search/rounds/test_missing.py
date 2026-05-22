"""Tests for the missing-search round (spec 007 T057)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform, Release
from romarr.search.rounds.missing import (
    DEFAULT_LIMIT,
    run_missing_search,
)


@dataclass
class _FakeReport:
    candidates: list[object]
    grabs: list[object]


async def _seed_release(
    session: AsyncSession,
    *,
    title: str,
    status: str = "wanted",
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


@pytest.mark.asyncio
async def test_default_limit_is_50() -> None:
    assert DEFAULT_LIMIT == 50


@pytest.mark.asyncio
async def test_run_missing_search_iterates_wanted_releases(
    async_session: AsyncSession,
) -> None:
    """Three wanted Releases → three search rounds, each with the
    Game's title + platform_id."""
    await _seed_release(async_session, title="Sonic")
    await _seed_release(async_session, title="Mario")
    await _seed_release(async_session, title="Zelda")

    captured: list[tuple[str, int]] = []

    async def _fake_search(session, query, platform_id):
        captured.append((query, platform_id))
        return _FakeReport(candidates=["c"], grabs=[])

    result = await run_missing_search(
        async_session, search_fn=_fake_search
    )
    assert result.total == 3
    assert result.succeeded == 3
    assert result.grabbed == 0
    titles = sorted(q for q, _ in captured)
    assert titles == ["Mario", "Sonic", "Zelda"]


@pytest.mark.asyncio
async def test_run_missing_search_skips_imported(
    async_session: AsyncSession,
) -> None:
    """Releases with status='imported' must NOT be probed by the
    missing-search round (those are cutoff-search territory)."""
    await _seed_release(
        async_session, title="Sonic", status="imported"
    )
    await _seed_release(
        async_session, title="Mario", status="wanted"
    )

    visited: list[str] = []

    async def _fake_search(session, query, platform_id):
        visited.append(query)
        return _FakeReport(candidates=[], grabs=[])

    result = await run_missing_search(
        async_session, search_fn=_fake_search
    )
    assert result.total == 1
    assert visited == ["Mario"]


@pytest.mark.asyncio
async def test_run_missing_search_skips_unmonitored(
    async_session: AsyncSession,
) -> None:
    """``monitored=false`` Releases get skipped — operator opted
    out of automatic search."""
    await _seed_release(
        async_session, title="Sonic", monitored=False
    )
    await _seed_release(async_session, title="Mario")

    async def _fake_search(session, query, platform_id):
        return _FakeReport(candidates=[], grabs=[])

    result = await run_missing_search(
        async_session, search_fn=_fake_search
    )
    assert result.total == 1


@pytest.mark.asyncio
async def test_run_missing_search_per_release_failure_does_not_abort(
    async_session: AsyncSession,
) -> None:
    """One release failing the search MUST NOT kill the whole
    sweep — the next release still gets probed."""
    r1 = await _seed_release(async_session, title="Sonic")
    await _seed_release(async_session, title="Mario")

    async def _flaky(session, query, platform_id):
        if query == "Sonic":
            raise RuntimeError("indexer down")
        return _FakeReport(candidates=["c"], grabs=[])

    result = await run_missing_search(
        async_session, search_fn=_flaky
    )
    assert result.total == 2
    assert result.succeeded == 1
    skipped = [o for o in result.outcomes if o.skipped]
    assert len(skipped) == 1
    assert skipped[0].release_id == r1.id


@pytest.mark.asyncio
async def test_run_missing_search_oldest_first(
    async_session: AsyncSession,
) -> None:
    """``order_by created_at ASC`` — oldest Release gets probed
    first. A higher ``limit`` than the row count visits all of
    them, so we infer order by checking the captured query
    sequence."""
    # Seed in deliberately-reverse alphabetical order so the
    # ascending creation order is C, B, A.
    await _seed_release(async_session, title="C")
    await _seed_release(async_session, title="B")
    await _seed_release(async_session, title="A")

    visited: list[str] = []

    async def _fake_search(session, query, platform_id):
        visited.append(query)
        return _FakeReport(candidates=[], grabs=[])

    await run_missing_search(async_session, search_fn=_fake_search)
    assert visited == ["C", "B", "A"]


@pytest.mark.asyncio
async def test_run_missing_search_respects_limit(
    async_session: AsyncSession,
) -> None:
    """``limit=2`` against five wanted Releases probes only the
    first two."""
    for title in ("Q1", "Q2", "Q3", "Q4", "Q5"):
        await _seed_release(async_session, title=title)

    async def _fake_search(session, query, platform_id):
        return _FakeReport(candidates=[], grabs=[])

    result = await run_missing_search(
        async_session, limit=2, search_fn=_fake_search
    )
    assert result.total == 2


# ---------------------------------------------------------------------------
# dispatch_best_for_game gates on the canonical match_score
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_best_for_game_gates_on_match_score() -> None:
    """The auto-grab floor is compared against the canonical
    match_score (the same 0-100 number the search UI shows) — not the
    raw score_breakdown total. A candidate below the floor is
    reported below_min_score and never dispatched."""
    from types import SimpleNamespace

    from romarr.search.rounds._shared import dispatch_best_for_game

    candidates = [
        SimpleNamespace(matched_game_id=5, rejection=None, match_score=40),
        SimpleNamespace(matched_game_id=5, rejection=None, match_score=59),
    ]

    outcome = await dispatch_best_for_game(
        None,  # type: ignore[arg-type]  # below_min_score returns before DB use
        game_id=5,
        candidates=candidates,
        min_score=80,
    )

    assert outcome["dispatched"] is False
    assert outcome["best_score"] == 59
    assert outcome["no_grab_reason"] == "below_min_score: 59/80"
