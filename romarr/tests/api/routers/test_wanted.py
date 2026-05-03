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
from sqlalchemy import select
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


# ---------------------------------------------------------------------------
# slice 101 — platformId filter
# ---------------------------------------------------------------------------


async def _seed_two_platforms_with_wanted_releases(
    engine: AsyncEngine,
) -> tuple[int, int]:
    """Two platforms (MD + GBA), one wanted Release on each.
    Returns (platform_md_id, platform_gba_id)."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        md = Platform(slug="md", name="Mega Drive", short_name="MD")
        gba = Platform(slug="gba", name="Game Boy Advance", short_name="GBA")
        session.add_all([md, gba])
        await session.flush()
        sonic_md = Game(
            platform_id=md.id, slug="sonic-md", title="Sonic (MD)"
        )
        sonic_gba = Game(
            platform_id=gba.id, slug="sonic-gba", title="Sonic (GBA)"
        )
        session.add_all([sonic_md, sonic_gba])
        await session.flush()
        session.add_all(
            [
                Release(
                    game_id=sonic_md.id,
                    name="Sonic (USA, MD)",
                    status="wanted",
                    monitored=True,
                ),
                Release(
                    game_id=sonic_gba.id,
                    name="Sonic (USA, GBA)",
                    status="wanted",
                    monitored=True,
                ),
            ]
        )
        await session.commit()
        return md.id, gba.id


@pytest.mark.asyncio
async def test_missing_platform_id_filter_keeps_only_one_platform(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    md_id, _ = await _seed_two_platforms_with_wanted_releases(api_engine)
    resp = await authed_client.get(
        f"/api/v3/wanted/missing?platformId={md_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 1
    assert body["records"][0]["name"] == "Sonic (USA, MD)"
    # slice 134 — `platformId` is denormalised onto every row.
    assert body["records"][0]["platformId"] == md_id


@pytest.mark.asyncio
async def test_cutoff_platform_id_filter_keeps_only_one_platform(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Same fixture but flip both releases to imported + cutoff_met=False
    so they show up on /cutoff."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    md_id, _ = await _seed_two_platforms_with_wanted_releases(api_engine)
    async with sm() as session:
        rows = (
            (await session.execute(select(Release))).scalars().all()
        )
        for r in rows:
            r.status = "imported"
            r.cutoff_met = False
        await session.commit()

    resp = await authed_client.get(
        f"/api/v3/wanted/cutoff?platformId={md_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 1
    assert body["records"][0]["name"] == "Sonic (USA, MD)"


@pytest.mark.asyncio
async def test_missing_platform_id_zero_rejected(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get("/api/v3/wanted/missing?platformId=0")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# slice 141 — q substring filter on Release.name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_q_filter_substring_match(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Three wanted releases named Sonic / Streets / Mario.
    `?q=so` keeps only Sonic (case-insensitive)."""
    game_id = await _seed_platform_and_game(api_engine)
    await _seed_release(api_engine, game_id=game_id, name="Sonic the Hedgehog")
    await _seed_release(api_engine, game_id=game_id, name="Streets of Rage")
    await _seed_release(api_engine, game_id=game_id, name="Mario Kart")

    resp = await authed_client.get("/api/v3/wanted/missing?q=so")
    assert resp.status_code == 200
    body = resp.json()
    names = [r["name"] for r in body["records"]]
    assert names == ["Sonic the Hedgehog"]


@pytest.mark.asyncio
async def test_missing_q_empty_ignored(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Whitespace-only `q` is ignored — full list returned."""
    game_id = await _seed_platform_and_game(api_engine)
    await _seed_release(api_engine, game_id=game_id, name="A")
    await _seed_release(api_engine, game_id=game_id, name="B")

    resp = await authed_client.get("/api/v3/wanted/missing?q=%20%20")
    assert resp.status_code == 200
    assert resp.json()["totalRecords"] == 2


# ---------------------------------------------------------------------------
# slice 157 — tagId filter on Wanted (mirror of slice 156 on Library)
# ---------------------------------------------------------------------------


async def _seed_game_with_tags(
    engine: AsyncEngine,
    *,
    title: str,
    tags: list[int],
    platform_slug: str = "megadrive",
) -> int:
    """Seed a Platform + Game (with tags) and return the Game id."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        # Use a fresh platform slug per call so successive seeds
        # in the same test don't trip the platform unique key.
        suffix = title.lower().replace(" ", "-")
        platform = Platform(
            slug=f"{platform_slug}-{suffix}",
            name="Mega Drive",
            short_name="MD",
            manufacturer="Sega",
        )
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"slug-{suffix}",
            title=title,
            tags=tags,
        )
        session.add(game)
        await session.flush()
        await session.commit()
        return game.id


@pytest.mark.asyncio
async def test_missing_tag_id_filter_keeps_matching_games(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    a = await _seed_game_with_tags(
        api_engine, title="Tagged-A", tags=[5, 9]
    )
    b = await _seed_game_with_tags(
        api_engine, title="Tagged-B", tags=[7]
    )
    await _seed_release(api_engine, game_id=a, name="A USA")
    await _seed_release(api_engine, game_id=b, name="B USA")

    resp = await authed_client.get("/api/v3/wanted/missing?tagId=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 1
    assert body["records"][0]["name"] == "A USA"


@pytest.mark.asyncio
async def test_missing_tag_id_filter_rejects_substring_collision(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The bracket-replace pattern avoids matching ``5`` against
    a game tagged ``[15]``."""
    real = await _seed_game_with_tags(
        api_engine, title="Tag5", tags=[5]
    )
    decoy = await _seed_game_with_tags(
        api_engine, title="Tag15", tags=[15]
    )
    await _seed_release(api_engine, game_id=real, name="real")
    await _seed_release(api_engine, game_id=decoy, name="decoy")

    resp = await authed_client.get("/api/v3/wanted/missing?tagId=5")
    assert resp.status_code == 200
    names = {row["name"] for row in resp.json()["records"]}
    assert "real" in names
    assert "decoy" not in names


@pytest.mark.asyncio
async def test_cutoff_tag_id_filter_keeps_matching_games(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Same shape as missing — verifies the helper works on the
    cutoff endpoint too."""
    a = await _seed_game_with_tags(
        api_engine, title="Cut-A", tags=[3]
    )
    b = await _seed_game_with_tags(
        api_engine, title="Cut-B", tags=[42]
    )
    await _seed_release(
        api_engine,
        game_id=a,
        name="A imported",
        status="imported",
        cutoff_met=False,
    )
    await _seed_release(
        api_engine,
        game_id=b,
        name="B imported",
        status="imported",
        cutoff_met=False,
    )

    resp = await authed_client.get("/api/v3/wanted/cutoff?tagId=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 1
    assert body["records"][0]["name"] == "A imported"


@pytest.mark.asyncio
async def test_missing_tag_id_filter_stacks_with_platform_and_q(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """tagId stacks with platformId + q the same way platformId
    + q stack today."""
    a = await _seed_game_with_tags(
        api_engine, title="Stack Game", tags=[2]
    )
    await _seed_release(api_engine, game_id=a, name="Combo USA")
    await _seed_release(api_engine, game_id=a, name="Other JPN")

    resp = await authed_client.get(
        "/api/v3/wanted/missing?tagId=2&q=combo"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 1
    assert body["records"][0]["name"] == "Combo USA"
