"""Cutoff-search round (spec 007 T058).

Iterates over imported Releases that are still below the
operator's quality cutoff, oldest-first, and runs one manual-
search round per Release. Each result feeds the same 13-step
decision pipeline; an upgrade lands when the pipeline scores
a candidate strictly above the existing Dump's score (FR-003a
upgrade rule).

Same shape + dependency-injection pattern as
:mod:`romarr.search.rounds.missing` — keeps the two rounds
sibling-symmetric so the operator UI can render their results
without per-mode special-casing.
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


@dataclass(frozen=True, slots=True)
class CutoffSearchOutcome:
    """Per-Release result of one cutoff-search probe."""

    release_id: int
    game_id: int
    title: str
    candidates: int
    grabs: int
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class CutoffSearchResult:
    """Aggregate result of one ``run_cutoff_search`` invocation."""

    total: int = 0
    succeeded: int = 0
    grabbed: int = 0
    outcomes: list[CutoffSearchOutcome] = field(default_factory=list)


SearchFn = Callable[
    ["AsyncSession", str, int],
    Awaitable[Any],
]


async def _default_search(
    session: "AsyncSession",
    query: str,
    platform_id: int,
) -> Any:
    from romarr.search._clients import make_indexer_client_factory
    from romarr.search.rounds.manual import run_manual_search

    factory = make_indexer_client_factory(session)
    return await run_manual_search(
        session=session,
        query=query,
        client_factory=factory,
        platform_id=platform_id,
    )


async def run_cutoff_search(
    session: "AsyncSession",
    *,
    limit: int = DEFAULT_LIMIT,
    search_fn: SearchFn | None = None,
) -> CutoffSearchResult:
    """Probe up to ``limit`` below-cutoff Releases, oldest-first.

    A Release is in scope when:
      - ``status='imported'`` (the file is on disk)
      - ``cutoff_met=false`` (operator's quality cutoff not yet
        reached — pipeline still wants an upgrade)
      - ``monitored=true``
    Sort key is ``created_at ASC`` for the same reason as
    ``run_missing_search``.
    """
    fn = search_fn or _default_search
    result = CutoffSearchResult()

    rows = (
        await session.execute(
            select(Release)
            .where(Release.status == "imported")
            .where(Release.cutoff_met.is_(False))
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
            result.outcomes.append(
                CutoffSearchOutcome(
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
                "search.cutoff.release_failed",
                extra={
                    "release_id": release.id,
                    "game_id": game.id,
                    "error": f"{exc.__class__.__name__}: {exc}",
                },
            )
            result.outcomes.append(
                CutoffSearchOutcome(
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
            CutoffSearchOutcome(
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
        "search.cutoff.complete",
        extra={
            "total": result.total,
            "succeeded": result.succeeded,
            "grabbed": result.grabbed,
        },
    )
    return result


__all__ = [
    "CutoffSearchOutcome",
    "CutoffSearchResult",
    "DEFAULT_LIMIT",
    "SearchFn",
    "run_cutoff_search",
]
