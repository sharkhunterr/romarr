"""ROM content-pack endpoint tests (slice 460).

Covers the ``/api/v3/rom-pack`` CRUD surface plus the ``/ingest``
trigger's status guard. The ingest pipeline itself is exercised
in ``tests/rom_packs/test_ingest.py`` — here we only assert the
router fires it and refuses a double-start.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import Platform, RomPack, RomPackItem
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


async def _seed_platform(api_engine: AsyncEngine) -> int:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(slug="gba", name="Game Boy Advance")
        session.add(platform)
        await session.commit()
        return platform.id


@pytest.mark.asyncio
async def test_list_empty(authed_client: httpx.AsyncClient) -> None:
    resp = await authed_client.get("/api/v3/rom-pack")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Global config (slice 464)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_get_creates_singleton_with_defaults(
    authed_client: httpx.AsyncClient,
) -> None:
    """First GET get-or-creates the singleton with the schema
    defaults — and ``/config`` resolves ahead of ``/{pack_id}``."""
    resp = await authed_client.get("/api/v3/rom-pack/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["download_dir"] == "/downloads/rom_packs"
    assert body["default_max_size_bytes"] is None


@pytest.mark.asyncio
async def test_config_update_persists(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.put(
        "/api/v3/rom-pack/config",
        json={
            "download_dir": "/data/rom_packs",
            "default_max_size_bytes": 10 * 1024**3,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["download_dir"] == "/data/rom_packs"

    # The update is durable + the singleton is reused (not duplicated).
    again = await authed_client.get("/api/v3/rom-pack/config")
    assert again.json()["download_dir"] == "/data/rom_packs"
    assert again.json()["default_max_size_bytes"] == 10 * 1024**3


@pytest.mark.asyncio
async def test_create_then_list_and_get(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    platform_id = await _seed_platform(api_engine)
    resp = await authed_client.post(
        "/api/v3/rom-pack",
        json={
            "name": "No-Intro GBA",
            "url": "https://example.com/gba.zip",
            "platform_id": platform_id,
            "max_size_bytes": 1024,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "No-Intro GBA"
    assert body["source_kind"] == "url"
    assert body["status"] == "pending"
    assert body["platform_slug"] == "gba"
    assert body["max_size_bytes"] == 1024
    pack_id = body["id"]

    listed = await authed_client.get("/api/v3/rom-pack")
    assert [p["id"] for p in listed.json()] == [pack_id]

    one = await authed_client.get(f"/api/v3/rom-pack/{pack_id}")
    assert one.status_code == 200
    assert one.json()["id"] == pack_id


@pytest.mark.asyncio
async def test_create_rejects_unknown_platform(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/rom-pack",
        json={
            "name": "Bad",
            "url": "https://example.com/x.zip",
            "platform_id": 99999,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["errorMessage"] == "platform_not_found"


@pytest.mark.asyncio
async def test_create_allows_null_platform(
    authed_client: httpx.AsyncClient,
) -> None:
    """A multi-platform pack pins no platform — per-ROM hashes
    scatter the contents at ingest time."""
    resp = await authed_client.post(
        "/api/v3/rom-pack",
        json={"name": "Mixed set", "url": "https://example.com/all.zip"},
    )
    assert resp.status_code == 201
    assert resp.json()["platform_id"] is None


@pytest.mark.asyncio
async def test_update_pack(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    platform_id = await _seed_platform(api_engine)
    created = await authed_client.post(
        "/api/v3/rom-pack",
        json={"name": "Old", "url": "https://example.com/old.zip"},
    )
    pack_id = created.json()["id"]
    resp = await authed_client.put(
        f"/api/v3/rom-pack/{pack_id}",
        json={"name": "New name", "platform_id": platform_id},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New name"
    assert resp.json()["platform_id"] == platform_id


@pytest.mark.asyncio
async def test_delete_pack_cascades_items(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        pack = RomPack(
            name="Doomed",
            source_kind="url",
            url="https://example.com/d.zip",
            status="done",
        )
        session.add(pack)
        await session.flush()
        session.add(
            RomPackItem(
                rom_pack_id=pack.id,
                original_filename="rom.gba",
                status="unmatched",
            )
        )
        await session.commit()
        pack_id = pack.id

    resp = await authed_client.delete(f"/api/v3/rom-pack/{pack_id}")
    assert resp.status_code == 204

    gone = await authed_client.get(f"/api/v3/rom-pack/{pack_id}")
    assert gone.status_code == 404
    async with sm() as session:
        remaining = (
            await session.execute(
                RomPackItem.__table__.select().where(
                    RomPackItem.rom_pack_id == pack_id
                )
            )
        ).all()
        assert remaining == []


@pytest.mark.asyncio
async def test_list_items_filters_by_status(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        pack = RomPack(
            name="P", source_kind="url", url="https://e.com/p.zip"
        )
        session.add(pack)
        await session.flush()
        session.add_all(
            [
                RomPackItem(
                    rom_pack_id=pack.id,
                    original_filename="a.gba",
                    status="imported",
                ),
                RomPackItem(
                    rom_pack_id=pack.id,
                    original_filename="b.gba",
                    status="unmatched",
                ),
            ]
        )
        await session.commit()
        pack_id = pack.id

    all_items = await authed_client.get(f"/api/v3/rom-pack/{pack_id}/items")
    assert {i["original_filename"] for i in all_items.json()} == {
        "a.gba",
        "b.gba",
    }
    unmatched = await authed_client.get(
        f"/api/v3/rom-pack/{pack_id}/items",
        params={"status_filter": "unmatched"},
    )
    assert [i["original_filename"] for i in unmatched.json()] == ["b.gba"]


@pytest.mark.asyncio
async def test_ingest_refuses_when_in_progress(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        pack = RomPack(
            name="Busy",
            source_kind="url",
            url="https://e.com/b.zip",
            status="downloading",
        )
        session.add(pack)
        await session.commit()
        pack_id = pack.id

    resp = await authed_client.post(f"/api/v3/rom-pack/{pack_id}/ingest")
    assert resp.status_code == 409
    assert resp.json()["errorMessage"] == "rom_pack_ingest_in_progress"


@pytest.mark.asyncio
async def test_ingest_404_for_missing_pack(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post("/api/v3/rom-pack/424242/ingest")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Triage — per-item resolution (slice 462)
# ---------------------------------------------------------------------------


async def _seed_pack_with_unmatched(
    api_engine: AsyncEngine,
    *,
    extracted_path: str | None = "/tmp/rom_pack/x.gba",
    unmatched_count: int = 1,
) -> tuple[int, int]:
    """Seed an ``awaiting_triage`` pack with one unmatched item.
    Returns ``(pack_id, item_id)``."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        pack = RomPack(
            name="Triage me",
            source_kind="url",
            url="https://e.com/t.zip",
            status="awaiting_triage",
            total_files=unmatched_count,
            unmatched_count=unmatched_count,
        )
        session.add(pack)
        await session.flush()
        item = RomPackItem(
            rom_pack_id=pack.id,
            original_filename="x.gba",
            extracted_path=extracted_path,
            size_bytes=4096,
            sha1="a" * 40,
            status="unmatched",
        )
        session.add(item)
        await session.commit()
        return pack.id, item.id


@pytest.mark.asyncio
async def test_park_item_settles_pack_when_last_unmatched(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Parking the only unmatched ROM drains the counter and
    flips the pack awaiting_triage → done."""
    pack_id, item_id = await _seed_pack_with_unmatched(api_engine)

    resp = await authed_client.post(
        f"/api/v3/rom-pack/{pack_id}/items/{item_id}/park"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "parked"

    pack = await authed_client.get(f"/api/v3/rom-pack/{pack_id}")
    assert pack.json()["unmatched_count"] == 0
    assert pack.json()["parked_count"] == 1
    assert pack.json()["status"] == "done"


@pytest.mark.asyncio
async def test_delete_item_marks_deleted_and_decrements(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    # Two unmatched — deleting one leaves the pack awaiting_triage.
    pack_id, item_id = await _seed_pack_with_unmatched(
        api_engine, unmatched_count=2
    )
    resp = await authed_client.delete(
        f"/api/v3/rom-pack/{pack_id}/items/{item_id}"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    pack = await authed_client.get(f"/api/v3/rom-pack/{pack_id}")
    assert pack.json()["unmatched_count"] == 1
    assert pack.json()["status"] == "awaiting_triage"


@pytest.mark.asyncio
async def test_triage_refuses_already_resolved_item(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    pack_id, item_id = await _seed_pack_with_unmatched(api_engine)
    # Resolve it once.
    await authed_client.post(
        f"/api/v3/rom-pack/{pack_id}/items/{item_id}/park"
    )
    # A second triage action is a 409 — the UI shouldn't offer it.
    again = await authed_client.delete(
        f"/api/v3/rom-pack/{pack_id}/items/{item_id}"
    )
    assert again.status_code == 409
    assert again.json()["errorMessage"] == "rom_pack_item_not_unmatched"


@pytest.mark.asyncio
async def test_associate_404_for_unknown_game(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    pack_id, item_id = await _seed_pack_with_unmatched(api_engine)
    resp = await authed_client.post(
        f"/api/v3/rom-pack/{pack_id}/items/{item_id}/associate",
        json={"game_id": 99999},
    )
    assert resp.status_code == 404
    assert resp.json()["errorMessage"] == "game_not_found"


@pytest.mark.asyncio
async def test_associate_409_when_file_missing(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The extracted ROM was purged off disk between ingest and
    triage — associate can't import a file that isn't there."""
    platform_id = await _seed_platform(api_engine)
    pack_id, item_id = await _seed_pack_with_unmatched(
        api_engine, extracted_path="/tmp/rom_pack/does-not-exist.gba"
    )
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        from romarr.domain.models import Game

        game = Game(platform_id=platform_id, slug="g", title="G")
        session.add(game)
        await session.commit()
        game_id = game.id

    resp = await authed_client.post(
        f"/api/v3/rom-pack/{pack_id}/items/{item_id}/associate",
        json={"game_id": game_id},
    )
    assert resp.status_code == 409
    assert resp.json()["errorMessage"] == "rom_pack_item_file_missing"


@pytest.mark.asyncio
async def test_grab_pack_404_for_unknown_platform(
    authed_client: httpx.AsyncClient,
) -> None:
    """The platform check short-circuits before any indexer
    dispatch — an unknown platform_id is a clean 404."""
    resp = await authed_client.post(
        "/api/v3/rom-pack/grab",
        json={
            "name": "Grab pack",
            "platform_id": 99999,
            "indexer_id": 1,
            "indexer_guid": "guid-1",
            "download_url": "https://example.com/pack.torrent",
            "title": "No-Intro GBA",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["errorMessage"] == "platform_not_found"


@pytest.mark.asyncio
async def test_triage_404_for_missing_item(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    pack_id, _ = await _seed_pack_with_unmatched(api_engine)
    resp = await authed_client.post(
        f"/api/v3/rom-pack/{pack_id}/items/424242/park"
    )
    assert resp.status_code == 404
    assert resp.json()["errorMessage"] == "rom_pack_item_not_found"
