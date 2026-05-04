"""DAT-sources endpoint tests (slice 267).

Read-only summary at ``GET /api/v3/dat-source`` — aggregates
``DatEntry`` rows by ``source``.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import DatEntry, Platform
from tests.api.test_auth_endpoints import _seed_admin_user


_seed_counter = 0


@pytest.fixture
async def authed_client(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> httpx.AsyncClient:
    await _seed_admin_user(api_engine)
    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert login.status_code == 204
    return api_client


async def _seed_dat_entries(
    api_engine: AsyncEngine,
    *,
    source: str,
    platform_count: int,
    entries_per_platform: int,
    contents_hash: str = "abc123",
) -> None:
    """Seed N platforms × M DatEntry rows per platform with the
    given source. Returns nothing; the test queries via the
    endpoint."""
    global _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        for _ in range(platform_count):
            _seed_counter += 1
            suffix = _seed_counter
            platform = Platform(
                slug=f"platform-{source}-{suffix}",
                name=f"P {source} {suffix}",
            )
            session.add(platform)
            await session.flush()
            for j in range(entries_per_platform):
                session.add(
                    DatEntry(
                        platform_id=platform.id,
                        source=source,
                        name=f"{source} entry {suffix}-{j}",
                        crc32=f"{(suffix * 100 + j):08x}",
                        dat_contents_hash=contents_hash,
                    )
                )
        await session.commit()


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_entries(
    authed_client: httpx.AsyncClient,
) -> None:
    """Fresh DB → empty summary list (no DatEntry rows)."""
    response = await authed_client.get("/api/v3/dat-source")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_groups_by_source_with_counts(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Each distinct ``source`` aggregates entry_count +
    platform_count over all its DatEntry rows."""
    await _seed_dat_entries(
        api_engine, source="no-intro", platform_count=2, entries_per_platform=3
    )
    await _seed_dat_entries(
        api_engine, source="redump", platform_count=1, entries_per_platform=5
    )

    response = await authed_client.get("/api/v3/dat-source")
    assert response.status_code == 200
    body = response.json()

    by_source = {row["source"]: row for row in body}
    assert "no-intro" in by_source
    assert by_source["no-intro"]["entry_count"] == 6
    assert by_source["no-intro"]["platform_count"] == 2
    assert "redump" in by_source
    assert by_source["redump"]["entry_count"] == 5
    assert by_source["redump"]["platform_count"] == 1


@pytest.mark.asyncio
async def test_carries_latest_updated_at(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The ``latest_updated_at`` field is populated when entries
    exist."""
    await _seed_dat_entries(
        api_engine, source="tosec", platform_count=1, entries_per_platform=2
    )

    response = await authed_client.get("/api/v3/dat-source")
    body = response.json()
    tosec = next((r for r in body if r["source"] == "tosec"), None)
    assert tosec is not None
    assert tosec["latest_updated_at"] is not None


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/dat-source")
    assert response.status_code == 401
