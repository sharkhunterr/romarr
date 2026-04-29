"""Async CRUD over :class:`romarr.metadata.models.MetadataCache`.

The aggregator only ever reads rows where ``expires_at > NOW()``;
expired rows are treated as "missing" so the caller re-fetches.
TTL is the only eviction (FR-016a) — there is no LRU sweep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from romarr.metadata.models import MetadataCache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _utc_aware(value: datetime) -> datetime:
    """SQLite + aiosqlite drops tzinfo on read; normalize to UTC-aware."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def get_cached(
    session: AsyncSession,
    *,
    provider_name: str,
    game_id: int,
) -> MetadataCache | None:
    """Return the live cache row for ``(provider, game)`` or None.

    "Live" means ``expires_at > now``. Expired rows are returned as
    None so the caller transparently re-fetches.
    """
    row = (
        await session.execute(
            select(MetadataCache).where(
                MetadataCache.provider_name == provider_name,
                MetadataCache.game_id == game_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if _utc_aware(row.expires_at) <= datetime.now(UTC):
        return None
    return row


async def put_cached(
    session: AsyncSession,
    *,
    provider_name: str,
    provider_game_id: str,
    game_id: int,
    data: dict[str, Any],
    ttl_seconds: int,
) -> MetadataCache:
    """Upsert a cache entry. ``fetched_at`` is set to ``now``.

    Conflict target is the UNIQUE on ``(provider_name, provider_game_id)``
    — re-ingesting the same response for the same provider/game replaces
    the cached payload (the constitutional "no duplicate cache rows"
    invariant).
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl_seconds)

    # SQLite supports ON CONFLICT DO UPDATE since 3.24; we depend on that
    # for both SQLite and PostgreSQL via the dialect-specific insert. The
    # SQLAlchemy core insert does not natively expose UPSERT, so we use
    # the SQLite-flavored construct — PostgreSQL has the same syntax.
    stmt = (
        sqlite_insert(MetadataCache)
        .values(
            provider_name=provider_name,
            provider_game_id=provider_game_id,
            game_id=game_id,
            data=data,
            fetched_at=now,
            expires_at=expires_at,
        )
        .on_conflict_do_update(
            index_elements=[
                MetadataCache.provider_name,
                MetadataCache.provider_game_id,
            ],
            set_={
                "game_id": game_id,
                "data": data,
                "fetched_at": now,
                "expires_at": expires_at,
            },
        )
    )
    await session.execute(stmt)
    await session.commit()
    row = (
        await session.execute(
            select(MetadataCache).where(
                MetadataCache.provider_name == provider_name,
                MetadataCache.provider_game_id == provider_game_id,
            )
        )
    ).scalar_one()
    return row


async def invalidate_cached(
    session: AsyncSession,
    *,
    provider_name: str,
    game_id: int,
) -> int:
    """Delete every cache row for ``(provider, game)``. Returns the count."""
    rows = (
        await session.execute(
            select(MetadataCache).where(
                MetadataCache.provider_name == provider_name,
                MetadataCache.game_id == game_id,
            )
        )
    ).scalars().all()
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)
