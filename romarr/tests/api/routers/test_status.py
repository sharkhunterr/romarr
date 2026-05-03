"""`/api/v3/system/status` Sonarr-shape tests (T036, T037).

Verifies the auth-tiered contract from spec 013:
  * unauthenticated callers receive ``{version, isProduction}``;
  * authenticated callers (any role) receive the Sonarr v3 + v4
    union field set.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import romarr
from romarr.domain.models import Dump, Game, Platform, Release
from romarr.importer.models import ImportHistory
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


# ---------------------------------------------------------------------------
# slice 104 — /api/v3/system/stats
# ---------------------------------------------------------------------------


async def _login(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_user(api_engine)
    resp = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_stats_zeroes_on_empty_database(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _login(api_client, api_engine)
    resp = await api_client.get("/api/v3/system/stats")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "totalGames",
        "totalReleases",
        "totalDumps",
        "monitoredGames",
        "wantedReleases",
        "imports24h",
        "importsSuccess24h",
    ):
        assert body[key] == 0


@pytest.mark.asyncio
async def test_stats_counts_aggregate_correctly(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Two games (one monitored, one not), three releases (two
    wanted+monitored, one imported), two dumps, three imports
    in the last hour (two successful)."""
    await _login(api_client, api_engine)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(slug="md", name="Mega Drive")
        session.add(platform)
        await session.flush()
        g1 = Game(
            platform_id=platform.id,
            slug="g1",
            title="G1",
            monitored=True,
        )
        g2 = Game(
            platform_id=platform.id,
            slug="g2",
            title="G2",
            monitored=False,
        )
        session.add_all([g1, g2])
        await session.flush()
        r_wanted_a = Release(
            game_id=g1.id, name="r-a", status="wanted", monitored=True
        )
        r_wanted_b = Release(
            game_id=g1.id, name="r-b", status="wanted", monitored=True
        )
        r_imported = Release(
            game_id=g2.id, name="r-i", status="imported", monitored=True
        )
        session.add_all([r_wanted_a, r_wanted_b, r_imported])
        await session.flush()
        d1 = Dump(
            release_id=r_imported.id,
            path="/lib/d1.zip",
            original_filename="d1.zip",
            size_bytes=1,
            format="zip",
            crc32="00000000",
            md5="0" * 32,
            sha1="a" * 40,
        )
        d2 = Dump(
            release_id=r_imported.id,
            path="/lib/d2.zip",
            original_filename="d2.zip",
            size_bytes=1,
            format="zip",
            crc32="00000001",
            md5="1" * 32,
            sha1="b" * 40,
        )
        session.add_all([d1, d2])
        recent = datetime.now(UTC) - timedelta(minutes=10)
        old = datetime.now(UTC) - timedelta(days=2)
        session.add_all(
            [
                ImportHistory(
                    source_path="/in/ok-1.zip",
                    imported_via="manual",
                    success=True,
                    correlation_id=str(uuid4()),
                    started_at=recent,
                ),
                ImportHistory(
                    source_path="/in/ok-2.zip",
                    imported_via="manual",
                    success=True,
                    correlation_id=str(uuid4()),
                    started_at=recent,
                ),
                ImportHistory(
                    source_path="/in/fail-1.zip",
                    imported_via="manual",
                    success=False,
                    correlation_id=str(uuid4()),
                    started_at=recent,
                ),
                ImportHistory(
                    source_path="/in/old.zip",
                    imported_via="manual",
                    success=True,
                    correlation_id=str(uuid4()),
                    started_at=old,
                ),
            ]
        )
        await session.commit()

    resp = await api_client.get("/api/v3/system/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalGames"] == 2
    assert body["totalReleases"] == 3
    assert body["totalDumps"] == 2
    assert body["monitoredGames"] == 1
    assert body["wantedReleases"] == 2
    assert body["imports24h"] == 3
    assert body["importsSuccess24h"] == 2


@pytest.mark.asyncio
async def test_stats_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/system/stats")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 105 — byPlatform breakdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_by_platform_empty_returns_no_rows(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """No platforms → empty `byPlatform` array (not null)."""
    await _login(api_client, api_engine)
    resp = await api_client.get("/api/v3/system/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["byPlatform"] == []


@pytest.mark.asyncio
async def test_stats_by_platform_groups_and_sums(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Two platforms; MD has 2 dumps totalling 3000 bytes, GBA has
    a wanted-only Release with no dump (still surfaces in the
    breakdown thanks to the LEFT-OUTER JOIN)."""
    await _login(api_client, api_engine)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        md = Platform(slug="md", name="Mega Drive")
        gba = Platform(slug="gba", name="Game Boy Advance")
        session.add_all([md, gba])
        await session.flush()
        g_md = Game(platform_id=md.id, slug="g-md", title="G MD")
        g_gba = Game(platform_id=gba.id, slug="g-gba", title="G GBA")
        session.add_all([g_md, g_gba])
        await session.flush()
        r_md = Release(game_id=g_md.id, name="r-md")
        r_gba = Release(
            game_id=g_gba.id, name="r-gba", status="wanted"
        )
        session.add_all([r_md, r_gba])
        await session.flush()
        session.add_all(
            [
                Dump(
                    release_id=r_md.id,
                    path="/lib/md-1.zip",
                    original_filename="md-1.zip",
                    size_bytes=1000,
                    format="zip",
                    crc32="00000010",
                    md5="0" * 32,
                    sha1="a" * 40,
                ),
                Dump(
                    release_id=r_md.id,
                    path="/lib/md-2.zip",
                    original_filename="md-2.zip",
                    size_bytes=2000,
                    format="zip",
                    crc32="00000011",
                    md5="1" * 32,
                    sha1="b" * 40,
                ),
            ]
        )
        await session.commit()

    resp = await api_client.get("/api/v3/system/stats")
    assert resp.status_code == 200
    body = resp.json()
    by_pl = {row["platformName"]: row for row in body["byPlatform"]}
    assert "Mega Drive" in by_pl and "Game Boy Advance" in by_pl
    md_row = by_pl["Mega Drive"]
    assert md_row["totalGames"] == 1
    assert md_row["totalReleases"] == 1
    assert md_row["totalDumps"] == 2
    assert md_row["totalSizeBytes"] == 3000
    gba_row = by_pl["Game Boy Advance"]
    assert gba_row["totalGames"] == 1
    assert gba_row["totalReleases"] == 1
    assert gba_row["totalDumps"] == 0
    assert gba_row["totalSizeBytes"] == 0
