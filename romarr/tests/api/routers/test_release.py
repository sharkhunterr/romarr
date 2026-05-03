"""Release write-endpoint tests (slice 98)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import Game, Platform, Release
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


_seed_counter = 0


async def _seed_release(api_engine: AsyncEngine) -> int:
    global _seed_counter
    _seed_counter += 1
    suffix = _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(slug=f"r-pl-{suffix}", name="Mega Drive")
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"r-g-{suffix}",
            title=f"Game {suffix}",
        )
        session.add(game)
        await session.flush()
        release = Release(
            game_id=game.id,
            name=f"Game {suffix} (USA)",
        )
        session.add(release)
        await session.commit()
        return release.id


@pytest.mark.asyncio
async def test_patch_release_toggles_monitored_to_false(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Release default monitored=True. PATCH flips and persists."""
    release_id = await _seed_release(api_engine)

    resp = await authed_client.patch(
        f"/api/v3/rom/release/{release_id}", json={"monitored": False}
    )
    assert resp.status_code == 200
    assert resp.json()["monitored"] is False
    assert resp.json()["id"] == release_id


@pytest.mark.asyncio
async def test_patch_release_toggles_back_to_true(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    release_id = await _seed_release(api_engine)
    await authed_client.patch(
        f"/api/v3/rom/release/{release_id}", json={"monitored": False}
    )
    resp = await authed_client.patch(
        f"/api/v3/rom/release/{release_id}", json={"monitored": True}
    )
    assert resp.status_code == 200
    assert resp.json()["monitored"] is True


@pytest.mark.asyncio
async def test_patch_release_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.patch(
        "/api/v3/rom/release/9999999", json={"monitored": False}
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "release_not_found"


@pytest.mark.asyncio
async def test_patch_release_rejects_unknown_fields(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """`extra=forbid` keeps the surface narrow — Release name /
    region / dump_status edits belong to the import pipeline,
    not to a hand-rolled PATCH."""
    release_id = await _seed_release(api_engine)
    resp = await authed_client.patch(
        f"/api/v3/rom/release/{release_id}",
        json={"monitored": False, "name": "Hacked"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_release_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.patch(
        "/api/v3/rom/release/1", json={"monitored": False}
    )
    assert resp.status_code == 401
