"""Search-history endpoint tests (T066)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.search.models import SearchHistory
from tests.search.api.conftest import seed_admin_and_login


async def _seed_history(
    api_engine: AsyncEngine, *, search_type: str, count: int = 1
) -> str:
    correlation_id = str(uuid.uuid4())
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        for i in range(count):
            session.add(
                SearchHistory(
                    search_type=search_type,
                    query=f"q-{i}",
                    results_count=i,
                    started_at=datetime.now(UTC),
                    correlation_id=correlation_id,
                )
            )
        await session.commit()
    return correlation_id


@pytest.mark.asyncio
async def test_list_history_returns_rows(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    await _seed_history(api_engine, search_type="manual", count=3)

    response = await api_client.get("/api/v3/rom/search/history")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_filter_by_search_type(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    await _seed_history(api_engine, search_type="manual", count=2)
    await _seed_history(api_engine, search_type="rss", count=1)

    response = await api_client.get(
        "/api/v3/rom/search/history",
        params={"search_type": "manual"},
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert all(r["search_type"] == "manual" for r in rows)


@pytest.mark.asyncio
async def test_history_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/rom/search/history")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_limit_parameter_caps_response(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    await _seed_history(api_engine, search_type="manual", count=5)

    response = await api_client.get(
        "/api/v3/rom/search/history",
        params={"limit": 2},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2
