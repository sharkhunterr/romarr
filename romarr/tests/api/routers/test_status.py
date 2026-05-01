"""`/api/v3/system/status` Sonarr-shape tests (T036, T037).

Verifies the auth-tiered contract from spec 013:
  * unauthenticated callers receive ``{version, isProduction}``;
  * authenticated callers (any role) receive the Sonarr v3 + v4
    union field set.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import romarr
from tests.api.test_auth_endpoints import _seed_admin_user

# ---------------------------------------------------------------------------
# T037 — public tier (no auth)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_unauthenticated_returns_minimal_shape(
    api_client: httpx.AsyncClient,
) -> None:
    """Unauthenticated callers get only ``{version, isProduction}``
    — sufficient for Sonarr-shape probe-recognition (Notifiarr,
    Recyclarr) without leaking topology data to scanners."""
    resp = await api_client.get("/api/v3/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "version": romarr.__version__,
        "isProduction": True,
    }


# ---------------------------------------------------------------------------
# T036 — authenticated tier (full v3 + v4 union)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_authenticated_returns_full_sonarr_shape(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Once a session is active, the response carries every
    documented field. The Sonarr v3 baseline (version /
    instanceName / urlBase / osName / runtimeVersion / appData /
    startTime / isProduction) plus the v4 additions
    (databaseType / databaseVersion / migrationVersion /
    runtimeName) are all present (FR-031, SC-001)."""
    await _seed_admin_user(api_engine)
    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert login.status_code == 204

    resp = await api_client.get("/api/v3/system/status")
    assert resp.status_code == 200
    body = resp.json()

    # Sonarr v3 baseline (FR-031 minimum set).
    expected_v3_keys = {
        "version",
        "isProduction",
        "instanceName",
        "urlBase",
        "osName",
        "runtimeVersion",
        "appData",
        "startTime",
    }
    # Sonarr v4 additions per the spec 013 clarification.
    expected_v4_keys = {
        "databaseType",
        "databaseVersion",
        "migrationVersion",
        "runtimeName",
    }
    assert (expected_v3_keys | expected_v4_keys).issubset(body.keys())

    assert body["version"] == romarr.__version__
    assert body["instanceName"] == "Romarr"
    assert body["isProduction"] is True
    assert body["runtimeName"] == "python"
    # databaseType reflects the underlying engine. The test
    # fixtures use SQLite.
    assert body["databaseType"].lower() == "sqlite"
    # startTime round-trips as an ISO-8601 string.
    assert body["startTime"].endswith("Z")


# ---------------------------------------------------------------------------
# Unauthenticated leakage check — public tier MUST NOT include any
# v3/v4 fields beyond version + isProduction.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_public_tier_does_not_leak_topology(
    api_client: httpx.AsyncClient,
) -> None:
    """Spec 013 clarification: unauthenticated scanners must NOT
    see ``urlBase``, ``osName``, ``runtimeVersion``, ``appData``,
    ``instanceName``, ``startTime``."""
    resp = await api_client.get("/api/v3/system/status")
    assert resp.status_code == 200
    forbidden = {
        "urlBase",
        "osName",
        "runtimeVersion",
        "appData",
        "instanceName",
        "startTime",
        "databaseType",
        "databaseVersion",
        "migrationVersion",
        "runtimeName",
    }
    assert forbidden.isdisjoint(resp.json().keys())
