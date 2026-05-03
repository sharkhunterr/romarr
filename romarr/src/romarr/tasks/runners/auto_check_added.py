"""AutoCheckAddedRunner (spec 012 T052).

Event-driven sibling of the cron-fired runners. Fires when the
``OnGameAdded`` channel publishes — the API layer / importer
calls the scheduler dispatcher with ``trigger="AutoCheckAdded"``
and the new game's ``game_id`` in the parameters. The runner
loads the game, runs one manual-search round scoped to the
game's title + platform, and reports how many candidates the
round produced.

Why a thin wrapper around :func:`run_manual_search`?
Sonarr/Radarr fire a search-on-add as a profile-aware action —
the round honours the current Quality / Region / Dump /
Language profiles, applies blocklist gates, and emits the same
``SearchRoundReport`` the manual UI consumes. Re-using the
existing pipeline means the auto-on-add path can never drift
from the manual path; both go through the same 13-step
decision pipeline.

The runner is registered with ``RUNNER_REGISTRY`` (via
``AutoCheckAddedAdapter``) but explicitly NOT scheduled in
APScheduler — see ``tasks/scheduler.py``'s job-type guard plus
``tasks/seeder.py``'s default catalogue entry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from sqlalchemy import select

from romarr.domain.models import Game

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AutoCheckAddedResult:
    """Outcome of one ``run_search_on_add`` invocation."""

    game_id: int
    title: str
    platform_id: int
    candidates: int
    grabs: int
    skipped: bool = False
    skip_reason: str | None = None


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


async def run_search_on_add(
    session: "AsyncSession",
    *,
    game_id: int,
    search_fn: SearchFn | None = None,
) -> AutoCheckAddedResult:
    """Search for ``game_id`` and return a structured result.

    Loads the Game row (so the runner has authoritative title +
    platform_id even if the OnGameAdded payload was stale), runs
    one manual search round, and reports the candidate / grab
    counts. A missing or deleted Game returns a structured
    ``skipped=True`` result rather than raising — the event was
    fired in good faith and the scheduler audit should reflect
    that the runner ran but had nothing to do.
    """
    fn = search_fn or _default_search

    game = (
        await session.execute(select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    if game is None:
        _logger.info(
            "tasks.auto_check_added.game_missing",
            extra={"game_id": game_id},
        )
        return AutoCheckAddedResult(
            game_id=game_id,
            title="",
            platform_id=0,
            candidates=0,
            grabs=0,
            skipped=True,
            skip_reason="game_not_found",
        )

    report = await fn(session, game.title, game.platform_id)

    candidates = list(getattr(report, "candidates", []) or [])
    grabs = list(getattr(report, "grabs", []) or [])
    _logger.info(
        "tasks.auto_check_added.complete",
        extra={
            "game_id": game.id,
            "platform_id": game.platform_id,
            "candidates": len(candidates),
            "grabs": len(grabs),
        },
    )
    return AutoCheckAddedResult(
        game_id=game.id,
        title=game.title,
        platform_id=game.platform_id,
        candidates=len(candidates),
        grabs=len(grabs),
    )


__all__ = [
    "AutoCheckAddedResult",
    "SearchFn",
    "run_search_on_add",
]
