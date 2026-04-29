"""metadata_cache CRUD tests (T008, T009 / FR-016a)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Game, Platform
from romarr.metadata.cache import get_cached, invalidate_cached, put_cached
from romarr.metadata.models import MetadataCache


async def _seed_game(session: AsyncSession) -> Game:
    p = Platform(slug="megadrive", name="Mega Drive")
    session.add(p)
    await session.flush()
    g = Game(platform_id=p.id, slug="sonic-1", title="Sonic the Hedgehog")
    session.add(g)
    await session.flush()
    await session.commit()
    return g


async def test_put_and_get_round_trip(async_session: AsyncSession) -> None:
    game = await _seed_game(async_session)
    row = await put_cached(
        async_session,
        provider_name="igdb",
        provider_game_id="42",
        game_id=game.id,
        data={"name": "Sonic the Hedgehog"},
        ttl_seconds=3600,
    )
    assert row.provider_name == "igdb"
    fetched = await get_cached(async_session, provider_name="igdb", game_id=game.id)
    assert fetched is not None
    assert fetched.data == {"name": "Sonic the Hedgehog"}


async def test_get_returns_none_when_expired(async_session: AsyncSession) -> None:
    game = await _seed_game(async_session)
    # Insert directly with an expires_at in the past.
    past = datetime.now(UTC) - timedelta(seconds=10)
    row = MetadataCache(
        provider_name="igdb",
        provider_game_id="99",
        game_id=game.id,
        data={"x": 1},
        fetched_at=past - timedelta(seconds=1),
        expires_at=past,
    )
    async_session.add(row)
    await async_session.commit()

    assert (
        await get_cached(async_session, provider_name="igdb", game_id=game.id)
    ) is None


async def test_unique_provider_game_constraint(
    async_session: AsyncSession,
) -> None:
    game = await _seed_game(async_session)
    # First row OK.
    async_session.add(
        MetadataCache(
            provider_name="igdb",
            provider_game_id="42",
            game_id=game.id,
            data={"a": 1},
            fetched_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await async_session.commit()

    # Second row with same (provider_name, provider_game_id) violates UNIQUE.
    async_session.add(
        MetadataCache(
            provider_name="igdb",
            provider_game_id="42",
            game_id=game.id,
            data={"a": 2},
            fetched_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_put_upserts_existing_row(async_session: AsyncSession) -> None:
    game = await _seed_game(async_session)
    await put_cached(
        async_session,
        provider_name="igdb",
        provider_game_id="42",
        game_id=game.id,
        data={"v": 1},
        ttl_seconds=3600,
    )
    await put_cached(
        async_session,
        provider_name="igdb",
        provider_game_id="42",
        game_id=game.id,
        data={"v": 2},
        ttl_seconds=3600,
    )
    row = await get_cached(async_session, provider_name="igdb", game_id=game.id)
    assert row is not None
    assert row.data == {"v": 2}


async def test_invalidate_deletes_rows(async_session: AsyncSession) -> None:
    game = await _seed_game(async_session)
    await put_cached(
        async_session,
        provider_name="igdb",
        provider_game_id="42",
        game_id=game.id,
        data={"v": 1},
        ttl_seconds=3600,
    )
    deleted = await invalidate_cached(
        async_session, provider_name="igdb", game_id=game.id
    )
    assert deleted == 1
    assert (
        await get_cached(async_session, provider_name="igdb", game_id=game.id)
    ) is None
