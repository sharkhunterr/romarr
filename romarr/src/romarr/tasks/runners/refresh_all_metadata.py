"""RefreshAllMetadataRunner (spec 012 T050).

Paginates over every Game and calls spec-002's
:func:`refresh_game_metadata` for each. Used by the scheduler
when the operator triggers a "refresh all metadata" job (no
``gameId`` parameter), or as a periodic cron once the
RefreshGameMetadataAdapter wires its all-games path through
this runner.

Design notes
------------

* Pagination is keyed on ``Game.id`` rather than offset to keep
  memory bounded — a fixed ``limit=N`` slice per round, then
  ``id > last_id`` for the next round. Avoids the
  ``OFFSET + LIMIT`` quadratic-in-N cost on large libraries.
* Per-Game errors are caught and counted; one bad provider
  shouldn't kill the whole job. The summary surfaces the
  failure count so operators can investigate via the per-Game
  refresh endpoint.
* Optional ``platform_id`` parameter restricts the sweep to a
  single Platform — useful for "refresh just the Mega Drive
  catalogue" runs.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from romarr.domain.models import Game

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)

# Page size — small enough to keep memory flat, large enough
# to amortise the round-trip overhead.
_PAGE_SIZE = 100


@dataclass
class RefreshAllMetadataResult:
    """Outcome of one ``refresh_all_metadata`` run."""

    total: int
    """Total number of Games visited (regardless of outcome)."""
    refreshed: int
    """Games whose ``refresh_game_metadata`` returned a result."""
    failed: int
    """Games whose refresh raised an exception."""
    last_game_id: int | None
    """The id of the last Game visited (or ``None`` if zero rows)."""


async def refresh_all_metadata(
    session: AsyncSession,
    *,
    platform_id: int | None = None,
    force: bool = False,
    page_size: int = _PAGE_SIZE,
    refresh_fn: Callable[..., Awaitable[Any]] | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> RefreshAllMetadataResult:
    """Sweep every Game (optionally scoped to one Platform) and
    refresh its metadata. Returns aggregate counts.

    ``refresh_fn`` is dependency-injected so tests can swap a
    deterministic stub for the real
    :func:`romarr.metadata.refresh.refresh_game_metadata`. The
    default is the production function.

    ``progress_callback`` — when given — is invoked after every
    game with ``(total_so_far, refreshed_so_far, failed_so_far)``.
    The Activity → Queue active-task card uses it to surface
    live counters; the callback is sync + best-effort so a
    misbehaving callback never sinks the sweep.
    """
    if refresh_fn is None:
        from romarr.metadata.refresh import refresh_game_metadata

        refresh_fn = refresh_game_metadata

    total = 0
    refreshed = 0
    failed = 0
    last_id: int | None = None

    cursor: int = 0
    while True:
        stmt = (
            select(Game.id)
            .where(Game.id > cursor)
            .order_by(Game.id.asc())
            .limit(page_size)
        )
        if platform_id is not None:
            stmt = stmt.where(Game.platform_id == platform_id)
        page = (await session.execute(stmt)).scalars().all()
        if not page:
            break
        for game_id in page:
            total += 1
            last_id = game_id
            try:
                await refresh_fn(session, game_id=game_id, force=force)
                refreshed += 1
            except Exception:
                # Per-Game failures shouldn't sink the whole
                # sweep — log + count and move on.
                _logger.warning(
                    "refresh_all_metadata.game_failed",
                    extra={"game_id": game_id},
                    exc_info=True,
                )
                failed += 1
            if progress_callback is not None:
                # Best-effort — never sink the sweep.
                with contextlib.suppress(Exception):
                    progress_callback(total, refreshed, failed)
        cursor = page[-1]
        if len(page) < page_size:
            break

    return RefreshAllMetadataResult(
        total=total,
        refreshed=refreshed,
        failed=failed,
        last_game_id=last_id,
    )


__all__ = [
    "RefreshAllMetadataResult",
    "refresh_all_metadata",
]
