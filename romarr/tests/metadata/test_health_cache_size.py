"""Tests for the metadata cache-size health check (CL008, FR-016a)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.models import Game, Platform
from romarr.metadata.health import (
    ERROR_THRESHOLD_GB,
    WARNING_THRESHOLD_GB,
    MetadataCacheSizeHealthCheck,
)
from romarr.metadata.models import MetadataCache
from romarr.notifications.types import HealthStatus


async def _seed_cache_rows(
    sm: async_sessionmaker[AsyncSession], *, rows: int
) -> None:
    """Seed ``rows`` ``metadata_cache`` entries so the size
    estimate trips the right threshold."""
    async with sm() as session:
        platform = Platform(slug="md", name="MD")
        session.add(platform)
        await session.flush()
        game = Game(platform_id=platform.id, slug="g", title="Game")
        session.add(game)
        await session.flush()
        now = datetime.now(UTC)
        for i in range(rows):
            session.add(
                MetadataCache(
                    provider_name="igdb",
                    provider_game_id=f"igdb-{i}",
                    game_id=game.id,
                    data={"k": "v"},
                    fetched_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_cache_size_ok_below_warning_threshold(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Empty / small cache → ``ok``."""
    sm = async_sessionmaker_factory

    async def _factory() -> AsyncSession:
        return sm()

    check = MetadataCacheSizeHealthCheck(session_factory=_factory)
    result = await check.run()
    assert result.status is HealthStatus.OK
    assert "0 rows" in result.message


@pytest.mark.asyncio
async def test_cache_size_warning_at_threshold(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Cross 2 GB → ``warning``. We seed enough rows that the
    estimate (rows × bytes_per_row) crosses the threshold."""
    sm = async_sessionmaker_factory

    async def _factory() -> AsyncSession:
        return sm()

    # bytes_per_row=1 GB makes a 3-row table cross the warning
    # threshold without seeding millions of rows.
    bytes_per_row = 1024**3  # 1 GiB per row
    await _seed_cache_rows(sm, rows=3)

    check = MetadataCacheSizeHealthCheck(
        session_factory=_factory,
        bytes_per_row=bytes_per_row,
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING
    assert f"{WARNING_THRESHOLD_GB:.0f} GB" in result.message


@pytest.mark.asyncio
async def test_cache_size_error_at_error_threshold(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Cross 4 GB → ``error``."""
    sm = async_sessionmaker_factory

    async def _factory() -> AsyncSession:
        return sm()

    bytes_per_row = 1024**3
    await _seed_cache_rows(sm, rows=5)  # 5 GB > 4 GB error threshold

    check = MetadataCacheSizeHealthCheck(
        session_factory=_factory,
        bytes_per_row=bytes_per_row,
    )
    result = await check.run()
    assert result.status is HealthStatus.ERROR
    assert f"{ERROR_THRESHOLD_GB:.0f} GB" in result.message


@pytest.mark.asyncio
async def test_cache_size_no_session_factory_returns_warning() -> None:
    """Misconfigured: no session factory wired — surfaces a
    structured warning rather than crashing the check cycle."""
    check = MetadataCacheSizeHealthCheck()
    result = await check.run()
    assert result.status is HealthStatus.WARNING
    assert "no session factory" in result.message
