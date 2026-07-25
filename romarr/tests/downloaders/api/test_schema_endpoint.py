"""GET /api/v3/downloadclient/schema (T061)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.downloaders.api.conftest import seed_admin_and_login


@pytest.mark.asyncio
async def test_schema_lists_real_impls_and_stubs(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.get("/api/v3/downloadclient/schema")
    assert response.status_code == 200
    rows = {r["implementation"]: r for r in response.json()}
    assert rows["qbittorrent"]["available"] is True
    assert rows["sabnzbd"]["available"] is True
    assert rows["deluge"]["available"] is True
    assert rows["transmission"]["available"] is False
    assert rows["nzbget"]["available"] is False
    # Real impls expose config fields; stubs do not.
    assert rows["qbittorrent"]["fields"]
    assert rows["sabnzbd"]["fields"]
    assert rows["deluge"]["fields"]
    assert rows["transmission"]["fields"] == []


@pytest.mark.asyncio
async def test_schema_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/downloadclient/schema")
    assert response.status_code == 401
