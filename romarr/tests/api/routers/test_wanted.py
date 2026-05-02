"""Wanted router tests (T042, FR-014).

Covers `/api/v3/wanted/missing` and `/api/v3/wanted/cutoff`.
The bulk-search endpoint (T043) is deferred to a follow-up
slice when the spec 007 ``run_manual_search`` hook is wired.

Releases have FK chains to Game → Platform; the helper seeds
the smallest viable set so the test stays focused on the
status-filter behaviour."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import Game, Platform, Release
from tests.api.test_auth_endpoints import _seed_admin_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_platform_and_game(engine: AsyncEngine) -> int:
    """Insert a Platform + Game; return the Game id so callers
    can attach Releases."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(
            slug="megadrive",
            name="Mega Drive",
            short_name="MD",
            manufacturer="Sega",
        )
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug="sonic-the-hedgehog",
            title="Sonic the Hedgehog",
        )
        session.add(game)
        await session.flush()
        await session.commit()
        return game.id


async def _seed_release(
    engine: AsyncEngine,
    *,
    game_id: int,
    name: str,
    status: str = "wanted",
    monitored: bool = True,
    cutoff_met: bool = False,
) -> int:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        release = Release(
            game_id=game_id,
            name=name,
            regions=["USA"],
            languages=["en"],
            status=status,
            monitored=monitored,
            cutoff_met=cutoff_met,
        )
        session.add(release)
        await session.flush()
        await session.commit()
        return release.id


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
# T042 — /missing returns the canonical envelope of wanted releases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_returns_only_wanted_monitored_releases(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """The /missing filter is ``status='wanted' AND
    monitored=true``. Imported and unmonitored rows are
    excluded."""
    game_id = await _seed_platform_and_game(api_engine)
    wanted_id = await _seed_release(
        api_engine, game_id=game_id, name="Sonic the Hedgehog (USA)"
    )
    # Imported — should not appear.
    await _seed_release(
        api_engine,
        game_id=game_id,
        name="Sonic the Hedgehog (EUR)",
        status="imported",
    )
    # Unmonitored wanted — also should not appear.
    await _seed_release(
        api_engine,
        game_id=game_id,
        name="Sonic the Hedgehog (JPN)",
        monitored=False,
    )

    resp = await authed_client.get("/api/v3/wanted/missing")
    assert resp.status_code == 200
    body = resp.json()

    # Canonical envelope.
    assert body["page"] == 1
    assert body["pageSize"] == 50
    assert body["totalRecords"] == 1
    assert len(body["records"]) == 1

    record = body["records"][0]
    assert record["id"] == wanted_id
    assert record["status"] == "wanted"
    assert record["monitored"] is True
    # Sonarr-shape camelCase fields.
    assert "gameId" in record
    assert "dumpStatus" in record
    assert "namingConvention" in record
    assert "cutoffMet" in record


@pytest.mark.asyncio
async def test_missing_paginates_and_sorts(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """``?pageSize=2`` caps the slice; ``?sortKey=name&sortDirection=desc``
    flips the order."""
    game_id = await _seed_platform_and_game(api_engine)
    for region in ("USA", "EUR", "JPN"):
        await _seed_release(
            api_engine,
            game_id=game_id,
            name=f"Sonic the Hedgehog ({region})",
        )

    resp = await authed_client.get(
        "/api/v3/wanted/missing"
        "?pageSize=2&sortKey=name&sortDirection=desc"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 3
    assert body["pageSize"] == 2
    assert body["sortKey"] == "name"
    assert body["sortDirection"] == "desc"
    names = [r["name"] for r in body["records"]]
    assert names == sorted(names, reverse=True)


# ---------------------------------------------------------------------------
# /cutoff — imported but not yet at the upgrade ceiling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cutoff_returns_imported_below_ceiling(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """The /cutoff filter is ``status='imported' AND
    cutoff_met=false AND monitored=true``. ``cutoff_met=true``
    rows are excluded — they're already at the operator's
    desired quality."""
    game_id = await _seed_platform_and_game(api_engine)
    upgrade_target = await _seed_release(
        api_engine,
        game_id=game_id,
        name="Sonic 2 (USA, low quality)",
        status="imported",
        cutoff_met=False,
    )
    # Already at target quality — excluded.
    await _seed_release(
        api_engine,
        game_id=game_id,
        name="Sonic 2 (USA, mint)",
        status="imported",
        cutoff_met=True,
    )
    # Wanted (not imported) — excluded.
    await _seed_release(
        api_engine,
        game_id=game_id,
        name="Sonic 2 (EUR)",
        status="wanted",
    )

    resp = await authed_client.get("/api/v3/wanted/cutoff")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 1
    assert body["records"][0]["id"] == upgrade_target
    assert body["records"][0]["status"] == "imported"
    assert body["records"][0]["cutoffMet"] is False


# ---------------------------------------------------------------------------
# Auth + invariants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/wanted/missing")
    assert resp.status_code == 401
    assert resp.json()["errorCode"] == "unauthenticated"


@pytest.mark.asyncio
async def test_cutoff_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/wanted/cutoff")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_invalid_sort_key_returns_400(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get(
        "/api/v3/wanted/missing?sortKey=NotARealField"
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "invalid_sort_key"
