"""Calendar router tests (T049, MVP).

Pins the empty-MVP contract so the frontend month-view can wire
against a stable shape. When a real data source lands the
``returns []`` invariant becomes ``returns matching events``,
but the schema (camelCase keys, ISO-8601 datetimes, validated
range) is locked in now.
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


# ---------------------------------------------------------------------------
# T049 — empty schema valid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_empty_list_with_valid_range(
    authed_client: httpx.AsyncClient,
) -> None:
    """MVP: any valid start/end range returns the empty list.
    Data sources are TBD; the schema is pinned."""
    resp = await authed_client.get(
        "/api/v3/calendar"
        "?start=2026-04-01T00:00:00Z&end=2026-05-01T00:00:00Z"
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_missing_start_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    """``start`` is required. FastAPI's query-param validator
    surfaces the missing field as 422."""
    resp = await authed_client.get(
        "/api/v3/calendar?end=2026-05-01T00:00:00Z"
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_end_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get(
        "/api/v3/calendar?start=2026-04-01T00:00:00Z"
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_inverted_range_returns_400(
    authed_client: httpx.AsyncClient,
) -> None:
    """``end <= start`` is a documented 400 with errorCode
    ``calendar_invalid_range`` (FR-008-style envelope)."""
    resp = await authed_client.get(
        "/api/v3/calendar"
        "?start=2026-05-01T00:00:00Z&end=2026-04-01T00:00:00Z"
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "calendar_invalid_range"


@pytest.mark.asyncio
async def test_equal_range_returns_400(
    authed_client: httpx.AsyncClient,
) -> None:
    """``end == start`` is also rejected — an empty range is a
    bug, not a feature."""
    resp = await authed_client.get(
        "/api/v3/calendar"
        "?start=2026-04-01T00:00:00Z&end=2026-04-01T00:00:00Z"
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "calendar_invalid_range"


@pytest.mark.asyncio
async def test_invalid_iso8601_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    """Pydantic's datetime validator catches malformed values."""
    resp = await authed_client.get(
        "/api/v3/calendar"
        "?start=not-a-date&end=2026-05-01T00:00:00Z"
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get(
        "/api/v3/calendar"
        "?start=2026-04-01T00:00:00Z&end=2026-05-01T00:00:00Z"
    )
    assert resp.status_code == 401
    assert resp.json()["errorCode"] == "unauthenticated"
