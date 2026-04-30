"""Manual-search endpoint tests (T061)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.search.api.conftest import seed_admin_and_login


@pytest.mark.asyncio
async def test_manual_search_returns_round_report(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """No indexers configured → empty round but the response shape
    is the documented :class:`SearchRoundReport` JSON."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/rom/search/manual",
        json={"query": "Sonic the Hedgehog"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["search_type"] == "manual"
    assert body["candidates"] == []
    assert body["grabs"] == []
    assert body["correlation_id"]
    assert body["indexer_outcomes"] == {}


@pytest.mark.asyncio
async def test_manual_search_validates_payload(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Empty query is rejected by the Pydantic min_length=1 validator."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/rom/search/manual",
        json={"query": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_manual_search_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/rom/search/manual", json={"query": "Sonic"}
    )
    assert response.status_code == 401
