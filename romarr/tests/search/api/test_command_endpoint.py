"""Sonarr-compat command endpoint tests (T065)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.search.api.conftest import seed_admin_and_login


@pytest.mark.asyncio
async def test_rss_sync_command_returns_completed(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """RssSync runs against zero indexers in this test environment —
    the round still returns a structured envelope."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/command",
        json={"name": "RssSync"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["name"] == "RssSync"
    assert body["status"] == "completed"


@pytest.mark.parametrize(
    "command_name",
    ["MissingSearch", "CutoffSearch", "IndexerSearch"],
)
@pytest.mark.asyncio
async def test_deferred_commands_acknowledged(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    command_name: str,
) -> None:
    """The other Sonarr-compat names return a structured deferred
    envelope so existing *arr tooling sees the request acknowledged
    without an HTTP error."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/command",
        json={"name": command_name},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["name"] == command_name
    assert body["status"] == "deferred"


@pytest.mark.asyncio
async def test_unknown_command_name_rejected(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Unknown command names hit the Pydantic Literal validator."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/command",
        json={"name": "BogusCommand"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_command_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/command", json={"name": "RssSync"}
    )
    assert response.status_code == 401
