"""Missing-search round (spec 007 T057).

Iterates over monitored ``Release`` rows whose ``status='wanted'``,
oldest-first, and runs one manual-search round per Release via
the existing ``run_manual_search`` orchestrator. Caps the sweep
at ``limit`` Releases per invocation so a long-running scheduled
trigger doesn't hold a single transaction open for hours.

The round is a thin coordinator: it picks the candidates and
delegates the actual indexer fan-out to ``run_manual_search``
so the 13-step decision pipeline stays the single source of
truth for grab decisions. ``search_fn`` is dependency-injected
so tests can short-circuit the network without spinning up
respx-mocked indexers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from sqlalchemy import select

from romarr.domain.models import Game, Release

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
"""Per-invocation cap. Each invocation does ``limit`` per-Release
search rounds; scheduling cron picks the cadence, this number
caps the cost of one tick."""


@dataclass(frozen=True, slots=True)
class MissingSearchOutcome:
    """Per-Release result of one missing-search probe."""

    release_id: int
    game_id: int
    title: str
    candidates: int
    grabs: int
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class MissingSearchResult:
    """Aggregate result of one ``run_missing_search`` invocation."""

    total: int = 0
    succeeded: int = 0
    grabbed: int = 0
    outcomes: list[MissingSearchOutcome] = field(default_factory=list)


SearchFn = Callable[
    ["AsyncSession", str, int],
    Awaitable[Any],
]
"""Async callable: ``(session, query, platform_id) -> SearchRoundReport``.

Tests inject a fake; the default builds the indexer client
factory and calls :func:`run_manual_search` directly.
"""


async def _default_search(
    session: "AsyncSession",
    query: str,
    platform_id: int,
) -> Any:
    """Production search path — runs one manual search round."""
    from romarr.search._clients import make_indexer_client_factory
    from romarr.search.rounds.manual import run_manual_search

    factory = make_indexer_client_factory(session)
    return await run_manual_search(
        session=session,
        query=query,
        client_factory=factory,
        platform_id=platform_id,
    )


async def run_missing_search(
    session: "AsyncSession",
    *,
    limit: int = DEFAULT_LIMIT,
    search_fn: SearchFn | None = None,
) -> MissingSearchResult:
    """Probe up to ``limit`` wanted Releases, oldest-first.

    A Release is "wanted" when:
      - ``status='wanted'`` (per the FR-003 lifecycle vocabulary)
      - ``monitored=true`` (operator hasn't opted out)
    Sort key is ``created_at ASC`` — Releases that have been
    waiting the longest get the next probe slot. ``last_searched_at``
    isn't on the schema today; ``created_at`` is a stable proxy
    that doesn't churn between rounds.
    """
    fn = search_fn or _default_search
    result = MissingSearchResult()

    rows = (
        await session.execute(
            select(Release)
            .where(Release.status == "wanted")
            .where(Release.monitored.is_(True))
            .order_by(Release.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    for release in rows:
        result.total += 1
        game = (
            await session.execute(
                select(Game).where(Game.id == release.game_id)
            )
        ).scalar_one_or_none()
        if game is None:
            # Cascade should have removed orphan Releases; if one
            # leaks through, count it as a structured skip instead
            # of crashing the whole round.
            result.outcomes.append(
                MissingSearchOutcome(
                    release_id=release.id,
                    game_id=release.game_id,
                    title="",
                    candidates=0,
                    grabs=0,
                    skipped=True,
                    skip_reason="game_not_found",
                )
            )
            continue
        try:
            report = await fn(session, game.title, game.platform_id)
        except Exception as exc:
            _logger.warning(
                "search.missing.release_failed",
                extra={
                    "release_id": release.id,
                    "game_id": game.id,
                    "error": f"{exc.__class__.__name__}: {exc}",
                },
            )
            result.outcomes.append(
                MissingSearchOutcome(
                    release_id=release.id,
                    game_id=game.id,
                    title=game.title,
                    candidates=0,
                    grabs=0,
                    skipped=True,
                    skip_reason=f"{exc.__class__.__name__}",
                )
            )
            continue

        candidates = list(getattr(report, "candidates", []) or [])
        # Manual search returns ``grabs=[]`` by contract (the
        # operator picks). For auto-grab paths we re-derive the
        # winner via the shared helper and dispatch it ourselves;
        # without this, every missing-search round logged "0
        # grabbed" even when a 93%-match candidate was sitting
        # right there. The score floor follows the game's
        # library binding so each release honours its own
        # profile cascade.
        from romarr.search.rounds._shared import (
            dispatch_best_for_game,
            load_min_score_for_game,
        )

        per_game_min_score = await load_min_score_for_game(
            session, game.id
        )
        dispatch_outcome = await dispatch_best_for_game(
            session,
            game_id=game.id,
            candidates=candidates,
            min_score=per_game_min_score,
        )
        skip_reason = (
            dispatch_outcome.get("no_grab_reason")
            if not dispatch_outcome.get("dispatched")
            else None
        )
        result.outcomes.append(
            MissingSearchOutcome(
                release_id=release.id,
                game_id=game.id,
                title=game.title,
                candidates=len(candidates),
                grabs=1 if dispatch_outcome.get("dispatched") else 0,
                skipped=False,
                skip_reason=skip_reason,
            )
        )
        result.succeeded += 1
        if dispatch_outcome.get("dispatched"):
            result.grabbed += 1

    _logger.info(
        "search.missing.complete",
        extra={
            "total": result.total,
            "succeeded": result.succeeded,
            "grabbed": result.grabbed,
        },
    )
    return result


__all__ = [
    "DEFAULT_LIMIT",
    "MissingSearchOutcome",
    "MissingSearchResult",
    "SearchFn",
    "run_missing_search",
]
