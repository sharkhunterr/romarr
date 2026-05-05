"""Exporter catalog endpoint tests (slice 279 / spec 009 T082).

Covers the read-only surface shipped today:
  * GET /api/v3/rom/exporters         → list
  * GET /api/v3/rom/exporters/{name}  → one
  * GET /api/v3/rom/exporters/unknown → 404

Per-import dispatch + ``POST /run`` are deferred to a future
slice when the spec 008 importer's per-import fan-out arrives.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.test_auth_endpoints import _seed_admin_user


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


@pytest.mark.asyncio
async def test_lists_the_four_documented_exporters(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/rom/exporters")
    assert response.status_code == 200
    body = response.json()
    names = {row["name"] for row in body}
    assert names == {"esde", "pegasus", "launchbox", "romm"}


@pytest.mark.asyncio
async def test_each_row_carries_format_metadata(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/rom/exporters")
    by_name = {row["name"]: row for row in response.json()}
    assert by_name["esde"]["format"] == "xml"
    assert by_name["pegasus"]["format"] == "txt"
    assert by_name["launchbox"]["format"] == "xml"
    assert by_name["romm"]["format"] == "http"
    for row in by_name.values():
        assert row["available"] is True
        assert isinstance(row["description"], str)
        assert len(row["description"]) > 0


@pytest.mark.asyncio
async def test_read_one_exporter_by_name(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/rom/exporters/esde")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "esde"
    assert body["format"] == "xml"


@pytest.mark.asyncio
async def test_unknown_name_returns_404(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/rom/exporters/not-a-real-one")
    assert response.status_code == 404
    # Spec-013 envelope unwraps to the top level via the app's
    # error handler; the route raises with a dict detail.
    assert response.json()["errorCode"] == "exporter_not_found"


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/rom/exporters")
    assert response.status_code == 401
