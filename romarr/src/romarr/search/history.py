"""Async search-history audit helpers (Phase 4 — STATE).

A round emits one row per (indexer, game) pair sharing one
``correlation_id`` (UUID). RSS sync rows have ``query=NULL``;
manual rounds carry the operator's text.

Per data-model.md, the audit table is system-written — no API
``Create`` / ``Update`` shape; operators only read it via the
history endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from romarr.search.models import SearchHistory

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.search.types import SearchType


async def record_round(
    session: AsyncSession,
    *,
    correlation_id: str,
    search_type: SearchType,
    query: str | None,
    indexer_results: Iterable[dict[str, Any]],
) -> list[SearchHistory]:
    """Write one row per (indexer, game) entry in ``indexer_results``.

    Each entry must carry: ``indexer_id``, ``game_id`` (nullable),
    ``release_id`` (nullable), ``results_count``, optional
    ``grabbed_release_id`` / ``chosen_indexer_guid`` / ``score`` /
    ``no_grab_reason`` / ``score_breakdown``. Timestamps are
    derived if not provided.

    Returns the persisted rows in input order so the orchestrator
    can fan downstream events out without re-querying.
    """
    now = datetime.now(UTC)
    rows: list[SearchHistory] = []
    for entry in indexer_results:
        rows.append(
            SearchHistory(
                search_type=search_type,
                query=query,
                indexer_id=entry.get("indexer_id"),
                game_id=entry.get("game_id"),
                release_id=entry.get("release_id"),
                results_count=int(entry.get("results_count", 0)),
                grabbed_release_id=entry.get("grabbed_release_id"),
                chosen_indexer_guid=entry.get("chosen_indexer_guid"),
                score=entry.get("score"),
                no_grab_reason=entry.get("no_grab_reason"),
                score_breakdown=entry.get("score_breakdown"),
                started_at=entry.get("started_at", now),
                finished_at=entry.get("finished_at", now),
                duration_ms=entry.get("duration_ms"),
                correlation_id=correlation_id,
            )
        )
    session.add_all(rows)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


__all__ = ["record_round"]
