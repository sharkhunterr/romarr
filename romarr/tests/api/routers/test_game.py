"""Game + Release read-endpoint tests (slice 86)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import Dump, Game, Platform, Release
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


async def _seed_chain(
    api_engine: AsyncEngine,
    *,
    title: str = "Sonic the Hedgehog",
    platform_slug: str = "megadrive",
    release_count: int = 1,
) -> tuple[int, int, list[int]]:
    """Seed Platform → Game → N Releases. Returns
    (platform_id, game_id, [release_id, ...])."""
    global _seed_counter
    _seed_counter += 1
    suffix = _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(
            slug=f"{platform_slug}-{suffix}", name="Mega Drive"
        )
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"sonic-{suffix}",
            title=title,
        )
        session.add(game)
        await session.flush()
        release_ids = []
        # Create N independent releases (different region tags) —
        # the multi-disc check constraint (disc_number > 1 implies
        # parent_release_id) makes a real disc-set fixture noisy
        # for a list test that just needs N rows for one game.
        for i in range(release_count):
            release = Release(
                game_id=game.id,
                name=f"{title} ({['USA', 'EUR', 'JPN'][i % 3]}) v{i}",
            )
            session.add(release)
            await session.flush()
            release_ids.append(release.id)
        await session.commit()
        return platform.id, game.id, release_ids


@pytest.mark.asyncio
async def test_list_games_returns_all(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_chain(api_engine, title="Sonic the Hedgehog")
    await _seed_chain(api_engine, title="Streets of Rage")

    response = await authed_client.get("/api/v3/game")
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert "Sonic the Hedgehog" in titles
    assert "Streets of Rage" in titles


@pytest.mark.asyncio
async def test_list_games_title_substring_filter(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_chain(api_engine, title="Sonic the Hedgehog")
    await _seed_chain(api_engine, title="Streets of Rage")

    response = await authed_client.get("/api/v3/game?q=sonic")
    assert response.status_code == 200
    body = response.json()
    titles = [row["title"] for row in body]
    assert all("Sonic" in t for t in titles)
    assert "Streets of Rage" not in titles


@pytest.mark.asyncio
async def test_list_games_empty_q_ignored(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_chain(api_engine, title="Sonic the Hedgehog")

    response = await authed_client.get("/api/v3/game?q=%20")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_list_games_platform_filter(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    pid_a, _, _ = await _seed_chain(api_engine, title="Sonic A")
    pid_b, _, _ = await _seed_chain(api_engine, title="Sonic B")

    response = await authed_client.get(f"/api/v3/game?platform_id={pid_a}")
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert "Sonic A" in titles
    assert "Sonic B" not in titles


@pytest.mark.asyncio
async def test_read_game_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/game/9999999")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_read_game_returns_full_shape(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, _ = await _seed_chain(api_engine, title="Sonic 2")

    response = await authed_client.get(f"/api/v3/game/{game_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == game_id
    assert body["title"] == "Sonic 2"
    assert "platform_id" in body
    assert "slug" in body


@pytest.mark.asyncio
async def test_list_releases_returns_all_for_game(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, release_ids = await _seed_chain(
        api_engine, title="Sonic CD", release_count=3
    )

    response = await authed_client.get(f"/api/v3/game/{game_id}/release")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    returned_ids = sorted(r["id"] for r in body)
    assert returned_ids == sorted(release_ids)


@pytest.mark.asyncio
async def test_list_releases_404_when_game_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/game/9999999/release")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_list_games_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/game")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# slice 95 — GET /api/v3/game/{id}/dump
# ---------------------------------------------------------------------------


async def _seed_dump_for_release(
    api_engine: AsyncEngine,
    *,
    release_id: int,
    path: str,
    sha1: str,
) -> int:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        dump = Dump(
            release_id=release_id,
            path=path,
            original_filename=path.rsplit("/", 1)[-1],
            size_bytes=1024,
            format="zip",
            crc32="00000000",
            md5="0" * 32,
            sha1=sha1,
        )
        session.add(dump)
        await session.commit()
        return dump.id


@pytest.mark.asyncio
async def test_list_dumps_for_game_joins_through_releases(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Two releases with one dump each → both surface in the
    per-game dump list."""
    _, game_id, release_ids = await _seed_chain(
        api_engine, title="Sonic Mania", release_count=2
    )
    d1 = await _seed_dump_for_release(
        api_engine,
        release_id=release_ids[0],
        path="/lib/mania-usa.zip",
        sha1="a" * 40,
    )
    d2 = await _seed_dump_for_release(
        api_engine,
        release_id=release_ids[1],
        path="/lib/mania-eur.zip",
        sha1="b" * 40,
    )

    resp = await authed_client.get(f"/api/v3/game/{game_id}/dump")
    assert resp.status_code == 200
    body = resp.json()
    returned_ids = sorted(d["id"] for d in body)
    assert returned_ids == sorted([d1, d2])
    paths = {d["path"] for d in body}
    assert paths == {"/lib/mania-usa.zip", "/lib/mania-eur.zip"}


@pytest.mark.asyncio
async def test_list_dumps_empty_when_no_dumps_imported(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A wanted-but-not-yet-imported game has zero dumps."""
    _, game_id, _ = await _seed_chain(api_engine, title="Wantedish")
    resp = await authed_client.get(f"/api/v3/game/{game_id}/dump")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_dumps_404_when_game_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get("/api/v3/game/9999999/dump")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_list_dumps_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/game/1/dump")
    assert resp.status_code == 401
