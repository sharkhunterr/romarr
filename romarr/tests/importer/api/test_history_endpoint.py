"""Import-history endpoint tests (T089, FR-038)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.importer.models import ImportHistory
from tests.importer.api.conftest import seed_user_and_login


async def _seed_rows(api_engine: AsyncEngine, count: int) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        for i in range(count):
            session.add(
                ImportHistory(
                    source_path=f"/downloads/rom-{i}.zip",
                    imported_via="manual" if i % 2 == 0 else "webhook",
                    success=i % 3 != 0,
                    correlation_id=str(uuid4()),
                    started_at=datetime.now(UTC),
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_list_history_paginated(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    await _seed_rows(api_engine, count=5)

    response = await api_client.get("/api/v3/rom/import/history?limit=2")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # Ordered by started_at desc — the most-recent inserts come first.
    assert body[0]["correlation_id"] is not None


@pytest.mark.asyncio
async def test_list_history_filter_by_imported_via(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    await _seed_rows(api_engine, count=4)

    response = await api_client.get(
        "/api/v3/rom/import/history?imported_via=manual"
    )
    assert response.status_code == 200
    rows = response.json()
    assert all(r["imported_via"] == "manual" for r in rows)
    # 2 of the 4 seeded rows are imported_via=manual (even indices).
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_list_history_filter_by_success(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    await _seed_rows(api_engine, count=6)

    failed = await api_client.get(
        "/api/v3/rom/import/history?success=false"
    )
    assert failed.status_code == 200
    rows = failed.json()
    assert all(r["success"] is False for r in rows)
    # i=0, 3 are failures (i % 3 == 0).
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_list_history_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/rom/import/history")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_history_validation_invalid_limit(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")

    too_big = await api_client.get("/api/v3/rom/import/history?limit=10000")
    assert too_big.status_code == 422

    too_small = await api_client.get("/api/v3/rom/import/history?limit=0")
    assert too_small.status_code == 422
