"""Game-match step (FR-013, FR-014, FR-015, FR-016 / pipeline step 6).

After identification produces a candidate title, the importer
needs to resolve it to an existing :class:`Game` on the target
platform. The match flow is:

  1. **Exact match** (case-insensitive) of any of the candidate
     titles against monitored Games on ``platform_id``. Confidence
     1.0.
  2. **Fuzzy match** via RapidFuzz's ``WRatio`` at threshold 90 —
     intentionally stricter than the search engine's 85 because a
     mistaken import is destructive (the file lands in the wrong
     Game's directory) whereas a mistaken search hit just shows up
     in a list.
  3. **Tie-break**: lower :attr:`Game.id` wins. Profile-region
     overlap (FR-015) is the orchestrator's concern — it ranks
     candidates returned by this step using the preloaded library
     bindings.
  4. **Suggested game** (FR-016): when no monitored Game matches
     above 90, retry against **unmonitored** Games at a stricter
     95 threshold; a hit populates ``suggested_game_id`` so the
     ``unidentified_dump`` row carries the operator-actionable
     hint without auto-creating a Release in an unmonitored Game.

The matching algorithm itself is **pure** — it consumes preloaded
candidate Games and emits a structured result. The DB query that
feeds it is a tiny helper at the bottom of the module so the
orchestrator can reuse the same pure core when it already has the
candidates in hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from rapidfuzz import fuzz, process
from sqlalchemy import select

from romarr.domain.models import Game

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


_MONITORED_THRESHOLD = 90
_SUGGESTED_THRESHOLD = 95


_MatchSignal = Literal[
    "title_exact", "title_fuzzy", "no_match", "suggested"
]


@dataclass(frozen=True)
class GameCandidate:
    """One Game in the matching pool.

    The renderer / matcher only needs ``id`` + ``title`` (+ a
    sort_title fallback) so the orchestrator can preload a slim
    query rather than full ORM instances.
    """

    id: int
    title: str
    sort_title: str | None = None
    monitored: bool = True


@dataclass(frozen=True)
class GameMatchResult:
    """Outcome of one ``match_to_game`` call.

    ``game_id`` is populated only when a monitored Game matched at
    or above the 90 threshold. ``suggested_game_id`` is populated
    only when an unmonitored Game matched at or above the 95
    threshold (FR-016 — operator-actionable hint, not an
    auto-import).
    """

    game_id: int | None
    confidence: float
    signal: _MatchSignal
    suggested_game_id: int | None = None
    candidates_considered: tuple[int, ...] = field(default_factory=tuple)


def _searchable(candidate: GameCandidate) -> tuple[str, ...]:
    out = [candidate.title]
    if candidate.sort_title and candidate.sort_title != candidate.title:
        out.append(candidate.sort_title)
    return tuple(out)


def _normalise(text: str) -> str:
    return text.strip().casefold()


def match_candidates(
    *,
    titles: Sequence[str],
    monitored: Sequence[GameCandidate],
    unmonitored: Sequence[GameCandidate] = (),
    monitored_threshold: int = _MONITORED_THRESHOLD,
    suggested_threshold: int = _SUGGESTED_THRESHOLD,
) -> GameMatchResult:
    """Pure matching algorithm. Consumes preloaded candidates +
    every title we know about (cascade name, parsed name, torznab
    title) and returns the best outcome.

    The caller is responsible for filtering monitored vs.
    unmonitored — we don't query the DB here. This keeps the
    function unit-testable in isolation.
    """
    cleaned = [t.strip() for t in titles if t and t.strip()]
    if not cleaned:
        return GameMatchResult(
            game_id=None,
            confidence=0.0,
            signal="no_match",
        )

    # 1. Exact (case-insensitive) match against monitored Games.
    monitored_by_canon: dict[str, GameCandidate] = {}
    for cand in monitored:
        for searchable in _searchable(cand):
            monitored_by_canon[_normalise(searchable)] = cand

    for title in cleaned:
        match = monitored_by_canon.get(_normalise(title))
        if match is not None:
            return GameMatchResult(
                game_id=match.id,
                confidence=1.0,
                signal="title_exact",
                candidates_considered=tuple(c.id for c in monitored),
            )

    # 2. RapidFuzz on monitored Games.
    fuzzy = _best_fuzzy(cleaned, monitored, monitored_threshold)
    if fuzzy is not None:
        return GameMatchResult(
            game_id=fuzzy[0].id,
            confidence=fuzzy[1] / 100.0,
            signal="title_fuzzy",
            candidates_considered=tuple(c.id for c in monitored),
        )

    # 3. Suggested-Game fallback against unmonitored Games at the
    # stricter 95 threshold (FR-016).
    if unmonitored:
        suggested = _best_fuzzy(cleaned, unmonitored, suggested_threshold)
        if suggested is not None:
            return GameMatchResult(
                game_id=None,
                confidence=suggested[1] / 100.0,
                signal="suggested",
                suggested_game_id=suggested[0].id,
                candidates_considered=tuple(c.id for c in unmonitored),
            )

    return GameMatchResult(
        game_id=None,
        confidence=0.0,
        signal="no_match",
        candidates_considered=tuple(c.id for c in monitored),
    )


def _best_fuzzy(
    titles: Sequence[str],
    pool: Sequence[GameCandidate],
    threshold: int,
) -> tuple[GameCandidate, float] | None:
    """Best (candidate, score) across every title x every pool
    member at or above ``threshold``. Tie-break: lower id (FR-015
    minimal version)."""
    if not pool:
        return None

    # Sort by id ascending so ``extractOne`` returns the lowest-id
    # candidate when scores tie (FR-015 minimal tie-break).
    sorted_pool = sorted(pool, key=lambda c: c.id)
    by_index: dict[int, GameCandidate] = dict(enumerate(sorted_pool))
    choices = {idx: " | ".join(_searchable(c)) for idx, c in by_index.items()}
    best: tuple[GameCandidate, float] | None = None

    for title in titles:
        result = process.extractOne(
            title,
            choices,
            scorer=fuzz.WRatio,
            processor=lambda s: _normalise(s) if isinstance(s, str) else s,
            score_cutoff=threshold,
        )
        if result is None:
            continue
        _, score, idx = result
        candidate = by_index[int(idx)]
        if best is None or score > best[1] or (
            score == best[1] and candidate.id < best[0].id
        ):
            best = (candidate, score)

    return best


async def load_candidates(
    session: AsyncSession, *, platform_id: int
) -> tuple[list[GameCandidate], list[GameCandidate]]:
    """Convenience query: load every Game on ``platform_id`` and
    split into monitored / unmonitored lists. The orchestrator can
    use this directly or hand the matcher a preloaded list when
    it already has the data on hand."""
    rows = (
        (
            await session.execute(
                select(Game).where(Game.platform_id == platform_id)
            )
        )
        .scalars()
        .all()
    )
    monitored: list[GameCandidate] = []
    unmonitored: list[GameCandidate] = []
    for row in rows:
        cand = GameCandidate(
            id=row.id,
            title=row.title,
            sort_title=row.sort_title,
            monitored=row.monitored,
        )
        (monitored if cand.monitored else unmonitored).append(cand)
    return monitored, unmonitored


async def match_to_game(
    *,
    session: AsyncSession,
    platform_id: int,
    titles: Sequence[str],
    monitored_threshold: int = _MONITORED_THRESHOLD,
    suggested_threshold: int = _SUGGESTED_THRESHOLD,
) -> GameMatchResult:
    """Async wrapper that loads candidates from the DB and runs
    :func:`match_candidates`. The pure ``match_candidates`` helper
    is preferred by tests and by the orchestrator's hot path
    (which preloads the candidate set once per import batch)."""
    monitored, unmonitored = await load_candidates(
        session, platform_id=platform_id
    )
    return match_candidates(
        titles=titles,
        monitored=monitored,
        unmonitored=unmonitored,
        monitored_threshold=monitored_threshold,
        suggested_threshold=suggested_threshold,
    )


__all__ = [
    "GameCandidate",
    "GameMatchResult",
    "load_candidates",
    "match_candidates",
    "match_to_game",
]
