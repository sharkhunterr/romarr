"""On-add search round (spec 007 T056).

Best-effort wrapper around ``run_manual_search`` invoked when a
new Game lands (operator added it via the Add UI, importer
created it from a found ROM, etc.). Mirrors the contract of
:func:`romarr.tasks.runners.auto_check_added.run_search_on_add`
but lives in the search-rounds namespace so the per-spec API
surface stays self-contained.

The two paths are intentionally redundant: the search-spec
caller (this module) is what an explicit
``POST /api/v3/rom/game/{id}/search`` handler will consume;
the tasks-spec caller (the ``AutoCheckAdded`` adapter) is
what the scheduler dispatches when ``OnGameAdded`` fires.
Both delegate to the same ``run_manual_search`` so the 13-step
decision pipeline stays the single source of truth.
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
class OnAddSearchResult:
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


async def _default_search(
    session: "AsyncSession",
    query: str,
    platform_id: int,
    game_id: int | None = None,
) -> Any:
    from romarr.search._clients import make_indexer_client_factory
    from romarr.search.rounds.manual import run_manual_search

    factory = make_indexer_client_factory(session)
    return await run_manual_search(
        session=session,
        query=query,
        client_factory=factory,
        platform_id=platform_id,
        search_type="auto_added",
        # Scope the round to the added game so the per-game
        # History tab gets ONE row instead of fanning out per
        # fuzzy-matched library sibling.
        requesting_game_id=game_id,
    )


async def run_search_on_add(
    session: "AsyncSession",
    *,
    game_id: int,
    search_fn: SearchFn | None = None,
) -> OnAddSearchResult:
    """Search for ``game_id`` once, best-effort.

    Best-effort means: a missing Game / failed search round /
    network error all surface as a structured ``skipped=True``
    result rather than raising. Callers (Add-flow handler,
    AutoCheckAdded scheduler adapter) want a no-op outcome
    when the indexers are unreachable, not an error that
    propagates up the API surface.
    """
    fn = search_fn or _default_search

    game = (
        await session.execute(select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    if game is None:
        return OnAddSearchResult(
            game_id=game_id,
            title="",
            platform_id=0,
            candidates=0,
            grabs=0,
            skipped=True,
            skip_reason="game_not_found",
        )

    try:
        # Identity-check the production default to flow
        # ``game_id`` down as ``requesting_game_id``; injected
        # test fakes keep the 3-arg legacy contract.
        if fn is _default_search:
            report = await _default_search(
                session, game.title, game.platform_id, game.id
            )
        else:
            report = await fn(session, game.title, game.platform_id)
    except Exception as exc:
        _logger.warning(
            "search.on_add.failed",
            extra={
                "game_id": game.id,
                "error": f"{exc.__class__.__name__}: {exc}",
            },
        )
        return OnAddSearchResult(
            game_id=game.id,
            title=game.title,
            platform_id=game.platform_id,
            candidates=0,
            grabs=0,
            skipped=True,
            skip_reason=f"{exc.__class__.__name__}",
        )

    candidates = list(getattr(report, "candidates", []) or [])
    grabs = list(getattr(report, "grabs", []) or [])
    return OnAddSearchResult(
        game_id=game.id,
        title=game.title,
        platform_id=game.platform_id,
        candidates=len(candidates),
        grabs=len(grabs),
    )


__all__ = ["OnAddSearchResult", "SearchFn", "run_search_on_add"]
