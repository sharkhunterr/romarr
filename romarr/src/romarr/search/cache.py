"""Async cache helpers for indexer search results (Phase 4 — STATE).

The cache stores raw indexer responses (gzipped) plus the canonical
``SearchResult`` projection JSON; non-RSS modes consult it before
firing an outbound HTTP call. Per FR-027, RSS sync ALWAYS bypasses
the cache — the bypass flag short-circuits the lookup so a stale
cache row can never poison RSS auto-grab decisions.

Cache key shape (FR-028 + plan.md research):

    cache_key = sha256(f"{query.lower().strip()}|{sorted_category_ids}").hex()

Stored alongside the row for diagnostics; the actual lookup uses the
hashed form so the index stays compact.

LRU eviction (FR-028a): when an INSERT would push the table past
10 000 rows, the helper runs a single bulk DELETE of the 1 000
oldest rows by ``last_read_at``. Hysteresis prevents thrashing.
"""

from __future__ import annotations

import gzip
import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from romarr.search.models import SearchCache

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession


CACHE_HARD_CAP = 10_000
"""LRU eviction triggers above this row count (FR-028a)."""

CACHE_LOW_WATER = 9_000
"""Eviction drains down to this row count (hysteresis)."""

DEFAULT_TTL_SECONDS = 3600
"""Per-indexer TTL when the indexer row carries no override."""


def cache_key_for(query: str, category_ids: Iterable[int]) -> str:
    """Compute the SHA-256 hex digest used as the cache key."""
    normalised_query = query.lower().strip()
    cat_part = ",".join(str(c) for c in sorted(set(category_ids)))
    payload = f"{normalised_query}|{cat_part}".encode()
    return hashlib.sha256(payload).hexdigest()


async def get_cached(
    session: AsyncSession,
    *,
    indexer_id: int,
    query: str,
    category_ids: Iterable[int],
    bypass: bool = False,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return the parsed-results JSON if cached + still fresh, else None.

    ``bypass=True`` short-circuits the lookup entirely — used by the
    RSS sync path so a stale cache row can never affect RSS results
    (FR-027).
    """
    if bypass:
        return None

    key = cache_key_for(query, category_ids)
    moment = now or datetime.now(UTC)

    row = (
        await session.execute(
            select(SearchCache)
            .where(SearchCache.indexer_id == indexer_id)
            .where(SearchCache.cache_key == key)
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    # SQLite drops tzinfo on round-trip; normalise both sides.
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    moment_naive = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    if moment_naive >= expires_at:
        # Past the TTL → treat as miss; the round orchestrator will
        # overwrite via put_cached on the fresh fetch.
        return None

    row.last_read_at = moment_naive
    await session.commit()
    return {
        "results": row.parsed_results,
        "fetched_at": row.fetched_at,
        "indexer_id": row.indexer_id,
        "cache_key": row.cache_key,
    }


async def put_cached(
    session: AsyncSession,
    *,
    indexer_id: int,
    query: str,
    category_ids: Iterable[int],
    response_xml: bytes,
    parsed_results: list[dict[str, Any]],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> None:
    """Insert (or replace) the cached row for this query."""
    key = cache_key_for(query, category_ids)
    moment = now or datetime.now(UTC)
    cats = sorted(set(category_ids))

    # Replace-on-conflict is cheaper than read-then-update for this
    # path; we don't need to know whether the row pre-existed.
    existing = (
        await session.execute(
            select(SearchCache)
            .where(SearchCache.indexer_id == indexer_id)
            .where(SearchCache.cache_key == key)
        )
    ).scalar_one_or_none()

    payload = {
        "indexer_id": indexer_id,
        "cache_key": key,
        "query": query,
        "category_ids": cats,
        "response_xml": gzip.compress(response_xml),
        "parsed_results": parsed_results,
        "fetched_at": moment,
        "expires_at": moment + timedelta(seconds=ttl_seconds),
        "last_read_at": moment,
    }

    if existing is not None:
        for key_, value in payload.items():
            setattr(existing, key_, value)
    else:
        session.add(SearchCache(**payload))

    try:
        await session.commit()
    except IntegrityError:
        # Race: another writer landed first. Roll back; the next read
        # will see the winner's row.
        await session.rollback()
        return

    await _maybe_evict_lru(session)


async def invalidate(
    session: AsyncSession, *, indexer_id: int, query: str, category_ids: Iterable[int]
) -> int:
    """Delete one cached row by its effective key. Returns rows deleted."""
    key = cache_key_for(query, category_ids)
    result: Any = await session.execute(
        delete(SearchCache)
        .where(SearchCache.indexer_id == indexer_id)
        .where(SearchCache.cache_key == key)
    )
    await session.commit()
    rowcount = getattr(result, "rowcount", 0) or 0
    return int(rowcount)


async def _maybe_evict_lru(session: AsyncSession) -> None:
    """Trim the cache table down to :data:`CACHE_LOW_WATER` rows when
    the count exceeds :data:`CACHE_HARD_CAP` (FR-028a)."""
    rows = list((await session.execute(select(SearchCache))).scalars().all())
    if len(rows) <= CACHE_HARD_CAP:
        return
    rows.sort(key=lambda r: r.last_read_at)
    drop_count = len(rows) - CACHE_LOW_WATER
    drop_ids = [r.id for r in rows[:drop_count]]
    if not drop_ids:
        return
    await session.execute(
        delete(SearchCache).where(SearchCache.id.in_(drop_ids))
    )
    await session.commit()


__all__ = [
    "CACHE_HARD_CAP",
    "CACHE_LOW_WATER",
    "DEFAULT_TTL_SECONDS",
    "cache_key_for",
    "get_cached",
    "invalidate",
    "put_cached",
]
