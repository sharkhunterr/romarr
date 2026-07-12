"""AutoCheckAddedRunner (spec 012 T052).

Event-driven sibling of the cron-fired runners. Fires when the
``OnGameAdded`` channel publishes — the API layer / importer
calls the scheduler dispatcher with ``trigger="AutoCheckAdded"``
and the new game's ``game_id`` in the parameters. The runner
loads the game, runs one manual-search round scoped to the
game's title + platform, dispatches the best candidate to the
download client, and reports the candidate / grab counts.

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

Tests inject 3-arg fakes; the production default below is a
4-arg overload (also takes ``game_id``) and gets selected via
identity check at the call site — that lets the production path
flow ``game_id`` down as ``requesting_game_id`` (one
``search_history`` row tied to the game instead of the fan-out
pattern that produced phantom rows under every Mario / Sonic
/ Layton sibling) without breaking the 3-arg test-fake contract.
"""


async def _default_search(
    session: "AsyncSession",
    query: str,
    platform_id: int,
    game_id: int | None = None,
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
        # Scope the round to the requesting game so the
        # search_history table records ONE row for it instead of
        # the fan-out pattern that produced phantom rows under
        # every Mario / Sonic / Layton sibling.
        requesting_game_id=game_id,
        # The round is the auto-check-added task firing — label
        # the row accordingly so the Activity feed distinguishes
        # it from operator-initiated manual searches.
        search_type="auto_added",
    )


DispatchFn = Callable[
    ["AsyncSession", int, list],
    Awaitable[bool],
]
"""Async callable: ``(session, game_id, candidates) -> dispatched``.

Tests inject a fake; the default re-derives the winning candidate
and dispatches it to the download client.
"""


async def _default_dispatch(
    session: "AsyncSession",
    game_id: int,
    candidates: list,
) -> bool:
    """Production grab path — ``run_manual_search`` returns
    ``grabs=[]`` by contract (the operator picks), so on-add (an
    auto-grab path, per :func:`dispatch_best_for_game`'s docstring)
    has to re-derive the winner and dispatch it itself, honouring
    the game's profile score floor — exactly like the missing /
    cutoff / rss rounds."""
    from romarr.search.rounds._shared import (
        dispatch_best_for_game,
        load_min_score_for_game,
    )

    min_score = await load_min_score_for_game(session, game_id)
    outcome = await dispatch_best_for_game(
        session,
        game_id=game_id,
        candidates=candidates,
        min_score=min_score,
    )
    return bool(outcome.get("dispatched"))


async def run_search_on_add(
    session: "AsyncSession",
    *,
    game_id: int,
    search_fn: SearchFn | None = None,
    dispatch_fn: DispatchFn | None = None,
) -> AutoCheckAddedResult:
    """Search for ``game_id``, grab the best candidate, and return
    a structured result.

    Loads the Game row (so the runner has authoritative title +
    platform_id even if the OnGameAdded payload was stale), runs
    one manual search round, then dispatches the winning candidate
    to the download client so a freshly-added game is actually
    acquired — not merely searched. A missing or deleted Game
    returns a structured ``skipped=True`` result rather than
    raising — the event was fired in good faith and the scheduler
    audit should reflect that the runner ran but had nothing to do.
    """
    fn = search_fn or _default_search
    dispatch = dispatch_fn or _default_dispatch

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

    # Identity check: when the production default is in use we
    # call its 4-arg overload directly (game_id → requesting_game_id
    # in the round). Injected test fakes keep the legacy 3-arg
    # contract so existing tests don't need to evolve in lock-step.
    if fn is _default_search:
        report = await _default_search(
            session, game.title, game.platform_id, game.id
        )
    else:
        report = await fn(session, game.title, game.platform_id)

    candidates = list(getattr(report, "candidates", []) or [])
    grabbed = await dispatch(session, game.id, candidates)
    grabs = 1 if grabbed else 0
    _logger.info(
        "tasks.auto_check_added.complete",
        extra={
            "game_id": game.id,
            "platform_id": game.platform_id,
            "candidates": len(candidates),
            "grabs": grabs,
        },
    )
    return AutoCheckAddedResult(
        game_id=game.id,
        title=game.title,
        platform_id=game.platform_id,
        candidates=len(candidates),
        grabs=grabs,
    )


__all__ = [
    "AutoCheckAddedResult",
    "DispatchFn",
    "SearchFn",
    "run_search_on_add",
]
