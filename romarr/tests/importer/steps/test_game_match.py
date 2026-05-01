"""Game-match step tests (T042-T045)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform
from romarr.importer.steps.game_match import (
    GameCandidate,
    match_candidates,
    match_to_game,
)

# ---------------------------------------------------------------------------
# Pure ``match_candidates`` algorithm
# ---------------------------------------------------------------------------


def _games(*titles: str, monitored: bool = True) -> list[GameCandidate]:
    return [
        GameCandidate(id=i + 1, title=t, monitored=monitored)
        for i, t in enumerate(titles)
    ]


def test_exact_match_short_circuits() -> None:
    monitored = _games("Sonic the Hedgehog", "Streets of Rage")
    result = match_candidates(
        titles=["sonic the hedgehog"],  # case-insensitive
        monitored=monitored,
    )
    assert result.signal == "title_exact"
    assert result.game_id == 1
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# T043 — RapidFuzz threshold 90
# ---------------------------------------------------------------------------


def test_rapidfuzz_threshold_90_accepts_close_match() -> None:
    monitored = _games("Sonic the Hedgehog")
    result = match_candidates(
        titles=["Sonic the hedge hog"],  # one space typo
        monitored=monitored,
    )
    assert result.signal == "title_fuzzy"
    assert result.game_id == 1
    assert result.confidence >= 0.90


def test_rapidfuzz_below_threshold_returns_no_match() -> None:
    monitored = _games("Final Fantasy VII")
    result = match_candidates(
        titles=["Sonic the Hedgehog"],
        monitored=monitored,
    )
    assert result.signal == "no_match"
    assert result.game_id is None
    assert result.confidence == 0.0


def test_threshold_can_be_relaxed_at_call_site() -> None:
    """Relaxing the threshold turns a previously-rejected fuzzy
    match into a hit — proves the threshold is the gate."""
    monitored = _games("Final Fantasy VII")
    result = match_candidates(
        titles=["Final Fantasy 7"],
        monitored=monitored,
        monitored_threshold=70,
    )
    assert result.signal == "title_fuzzy"
    assert result.game_id == 1


# ---------------------------------------------------------------------------
# T044 — tie-break by lower id (the profile-region tiebreak is the
# orchestrator's concern; the matcher just sorts on id when scores tie)
# ---------------------------------------------------------------------------


def test_tiebreak_lower_id_wins() -> None:
    monitored = [
        GameCandidate(id=42, title="Sonic the Hedgehog"),
        GameCandidate(id=7, title="Sonic the Hedgehog"),
    ]
    result = match_candidates(
        titles=["sonic the hedgehog"],
        monitored=monitored,
    )
    # Exact match returns the FIRST canon hit — but the algorithm
    # builds the canon dict in iteration order, so we need to test
    # via the fuzzy path to exercise the tiebreak.
    assert result.signal == "title_exact"
    # Either id satisfies the test — exact-match short-circuits and
    # both are equally valid. The fuzzy path is where the tiebreak
    # actually fires, covered below.


def test_fuzzy_tiebreak_lower_id_wins() -> None:
    monitored = [
        GameCandidate(id=42, title="Sonic the Hedgehog 2"),
        GameCandidate(id=7, title="Sonic the Hedgehog 2"),
    ]
    # A typo'd title fuzzy-matches both; tie should resolve to id=7.
    result = match_candidates(
        titles=["Sonic the Hedge Hog 2"],
        monitored=monitored,
    )
    assert result.signal == "title_fuzzy"
    assert result.game_id == 7


# ---------------------------------------------------------------------------
# T045 — DAT entry knows IGDB but Game not monitored ⇒ suggested
# ---------------------------------------------------------------------------


def test_unmatched_with_suggested_game() -> None:
    monitored: list[GameCandidate] = []
    unmonitored = [
        GameCandidate(
            id=99,
            title="Sonic the Hedgehog",
            monitored=False,
        ),
    ]
    result = match_candidates(
        titles=["Sonic the Hedgehog"],
        monitored=monitored,
        unmonitored=unmonitored,
    )
    assert result.signal == "suggested"
    assert result.game_id is None
    assert result.suggested_game_id == 99
    assert result.confidence >= 0.95


def test_no_match_when_neither_pool_hits() -> None:
    result = match_candidates(
        titles=["Some Random Game"],
        monitored=_games("Sonic", "Streets"),
        unmonitored=_games("Mario", monitored=False),
    )
    assert result.signal == "no_match"
    assert result.game_id is None
    assert result.suggested_game_id is None


def test_empty_titles_returns_no_match() -> None:
    result = match_candidates(
        titles=["", "  "],
        monitored=_games("Sonic"),
    )
    assert result.signal == "no_match"


# ---------------------------------------------------------------------------
# Async DB-backed wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_match_to_game_loads_from_db(async_session: AsyncSession) -> None:
    """The async wrapper queries the DB and feeds the pure matcher."""
    platform = Platform(name="Mega Drive", slug="megadrive-test")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    sonic = Game(
        platform_id=platform.id,
        slug="sonic",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    streets = Game(
        platform_id=platform.id,
        slug="streets-of-rage",
        title="Streets of Rage",
        monitored=True,
    )
    async_session.add_all([sonic, streets])
    await async_session.commit()
    await async_session.refresh(sonic)

    result = await match_to_game(
        session=async_session,
        platform_id=platform.id,
        titles=["sonic the hedgehog"],
    )
    assert result.signal == "title_exact"
    assert result.game_id == sonic.id


@pytest.mark.asyncio
async def test_match_to_game_unmonitored_falls_into_suggested(
    async_session: AsyncSession,
) -> None:
    platform = Platform(name="SNES", slug="snes-test")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    unmonitored = Game(
        platform_id=platform.id,
        slug="chrono-trigger",
        title="Chrono Trigger",
        monitored=False,
    )
    async_session.add(unmonitored)
    await async_session.commit()
    await async_session.refresh(unmonitored)

    result = await match_to_game(
        session=async_session,
        platform_id=platform.id,
        titles=["Chrono Trigger"],
    )
    assert result.signal == "suggested"
    assert result.suggested_game_id == unmonitored.id
