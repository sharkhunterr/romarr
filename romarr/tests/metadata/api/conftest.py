"""Module-local fixtures for metadata API tests.

Sets the deterministic ``ROMARR_AUTH_SECRET_KEY`` so the encryption
helper can derive a stable Fernet key, points ``ROMARR_DATA_DIR`` at
a per-test tmp dir for cover writes, and provides a couple of small
seeders for ``MetadataProviderConfig`` rows (Alembic isn't run by the
``api_engine`` fixture — it uses ``Base.metadata.create_all``).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.config.settings import get_settings
from romarr.metadata.models import MetadataProviderConfig


@pytest.fixture
def metadata_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret-key-do-not-use-in-prod")
    monkeypatch.setenv("ROMARR_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


async def seed_provider_rows(engine: AsyncEngine) -> None:
    """Seed the 9-provider table the same way migration 0002 does."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    rows = (
        ("igdb", 10, 4, 8),
        ("screenscraper", 20, 2, 4),
        ("mobygames", 30, 1, 2),
        ("launchbox", 40, 5, 10),
        ("hasheous", 50, 5, 10),
        ("playmatch", 60, 5, 10),
        ("retroachievements", 70, 5, 10),
        ("howlongtobeat", 80, 5, 10),
        ("steamgriddb", 90, 5, 10),
    )
    now = datetime.now(UTC)
    async with sm() as session:
        for name, priority, rps, burst in rows:
            existing = (
                await session.execute(
                    select(MetadataProviderConfig).where(
                        MetadataProviderConfig.provider_name == name
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            session.add(
                MetadataProviderConfig(
                    provider_name=name,
                    enabled=False,
                    priority_global=priority,
                    cache_ttl_seconds=2_592_000,
                    rate_limit_rps=rps,
                    rate_limit_burst=burst,
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()
