"""Library CRUD endpoint tests (T072-T075)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release
from romarr.libraries.models import Library
from tests.libraries.api.conftest import seed_profiles, seed_user_and_login


def _payload(*, tmp_library_path: Path, profile_ids: dict[str, int]) -> dict:
    return {
        "name": "Cartridges",
        "path": str(tmp_library_path),
        **profile_ids,
    }


@pytest.fixture
def tmp_library_path(tmp_path: Path) -> Path:
    """A real, writable directory for FR-004 path validation."""
    root = tmp_path / "library"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# T072 — full CRUD round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_crud_round_trip(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_library_path: Path,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    profile_ids = await seed_profiles(api_engine)

    # Create
    create_resp = await api_client.post(
        "/api/v3/rom/library",
        json=_payload(tmp_library_path=tmp_library_path, profile_ids=profile_ids),
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    library_id = body["id"]
    assert body["name"] == "Cartridges"
    assert body["lifecycle_policy"] == "hardlink_and_seed"
    assert body["is_romm_configured"] is False
    assert body["status"] == "ok"

    # List
    list_resp = await api_client.get("/api/v3/rom/library")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Read
    read_resp = await api_client.get(f"/api/v3/rom/library/{library_id}")
    assert read_resp.status_code == 200
    assert read_resp.json()["id"] == library_id

    # Update
    update_resp = await api_client.put(
        f"/api/v3/rom/library/{library_id}",
        json={"min_disk_free_gb": 20, "lifecycle_policy": "copy_and_keep"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["min_disk_free_gb"] == 20
    assert update_resp.json()["lifecycle_policy"] == "copy_and_keep"

    # Delete (no attached releases → no force needed)
    delete_resp = await api_client.delete(f"/api/v3/rom/library/{library_id}")
    assert delete_resp.status_code == 204

    # Read after delete → 404
    final = await api_client.get(f"/api/v3/rom/library/{library_id}")
    assert final.status_code == 404


# ---------------------------------------------------------------------------
# T073 — path validation 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_with_nonexistent_path_creates_directory(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """Slice 370: a missing target path is mkdir'd automatically
    so operators don't have to shell into the host before
    creating a library. The ``path_unwritable`` 400 still fires
    when the parent directory is not actually writable — covered
    by ``test_post_with_path_pointing_to_file_returns_400``."""
    await seed_user_and_login(api_engine, api_client, role="admin")
    profile_ids = await seed_profiles(api_engine)

    target = tmp_path / "missing"
    assert not target.exists()
    resp = await api_client.post(
        "/api/v3/rom/library",
        json=_payload(
            tmp_library_path=target,
            profile_ids=profile_ids,
        ),
    )
    assert resp.status_code == 201, resp.text
    assert target.is_dir()


@pytest.mark.asyncio
async def test_post_with_path_pointing_to_file_returns_400(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """A path that points to a regular file (not a directory)
    fails ``path_unwritable`` so the validator never overwrites
    a user's data with a library checkpoint."""
    await seed_user_and_login(api_engine, api_client, role="admin")
    profile_ids = await seed_profiles(api_engine)

    file_path = tmp_path / "regular-file.txt"
    file_path.write_text("placeholder")

    resp = await api_client.post(
        "/api/v3/rom/library",
        json=_payload(
            tmp_library_path=file_path,
            profile_ids=profile_ids,
        ),
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "path_unwritable"


@pytest.mark.asyncio
async def test_post_with_relative_path_returns_422(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    profile_ids = await seed_profiles(api_engine)

    resp = await api_client.post(
        "/api/v3/rom/library",
        json={"name": "Bad", "path": "relative/library", **profile_ids},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
    tmp_library_path: Path,
) -> None:
    resp = await api_client.post(
        "/api/v3/rom/library",
        json={
            "name": "Bad",
            "path": str(tmp_library_path),
            "quality_profile_id": 1,
            "region_profile_id": 1,
            "dump_profile_id": 1,
            "language_profile_id": 1,
            "naming_profile_id": 1,
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_list_readonly_role_allowed(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Readers are allowed to list libraries (FR-032a)."""
    await seed_user_and_login(api_engine, api_client, role="user")
    resp = await api_client.get("/api/v3/rom/library")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_post_user_role_forbidden(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_library_path: Path,
) -> None:
    """Non-admins cannot create libraries (FR-032a)."""
    await seed_user_and_login(api_engine, api_client, role="user")
    profile_ids = await seed_profiles(api_engine)
    resp = await api_client.post(
        "/api/v3/rom/library",
        json=_payload(tmp_library_path=tmp_library_path, profile_ids=profile_ids),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# T074 — force-delete blocked when keep_dump_history + historical Dumps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_delete_blocks_when_history_present(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_library_path: Path,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    profile_ids = await seed_profiles(api_engine)

    create_resp = await api_client.post(
        "/api/v3/rom/library",
        json={
            **_payload(tmp_library_path=tmp_library_path, profile_ids=profile_ids),
            "keep_dump_history": True,
        },
    )
    library_id = create_resp.json()["id"]

    # Seed a Release + Dump bound to this library to simulate history.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(name="Mega Drive", slug="megadrive")
        session.add(platform)
        await session.commit()
        await session.refresh(platform)

        game = Game(platform_id=platform.id, title="Sonic", slug="sonic")
        session.add(game)
        await session.commit()
        await session.refresh(game)

        release = Release(
            game_id=game.id,
            name="Sonic the Hedgehog (USA)",
            regions=["USA"],
            languages=["en"],
            dump_status=DumpStatus.VERIFIED,
            naming_convention=NamingConvention.NO_INTRO,
            library_id=library_id,
        )
        session.add(release)
        await session.commit()
        await session.refresh(release)

        dump = Dump(
            release_id=release.id,
            path=f"/var/lib/romarr/{library_id}/sonic.zip",
            original_filename="sonic.zip",
            size_bytes=1_000_000,
            format="zip",
            crc32="aabbccdd",
            md5="0" * 32,
            sha1="0" * 40,
        )
        session.add(dump)
        await session.commit()

    # Even with ?force=true, the historical-dump gate (FR-027) wins.
    resp = await api_client.delete(
        f"/api/v3/rom/library/{library_id}?force=true"
    )
    assert resp.status_code == 409
    assert resp.json()["errorCode"] == "historical_dumps_present"


# ---------------------------------------------------------------------------
# T075 — force-delete unbinds Releases when no Dump history kept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_delete_unbinds_releases_when_no_history(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_library_path: Path,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    profile_ids = await seed_profiles(api_engine)

    create_resp = await api_client.post(
        "/api/v3/rom/library",
        json={
            **_payload(tmp_library_path=tmp_library_path, profile_ids=profile_ids),
            "keep_dump_history": False,
        },
    )
    library_id = create_resp.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(name="Mega Drive", slug="megadrive")
        session.add(platform)
        await session.commit()
        await session.refresh(platform)

        game = Game(platform_id=platform.id, title="Sonic", slug="sonic")
        session.add(game)
        await session.commit()
        await session.refresh(game)

        release = Release(
            game_id=game.id,
            name="Sonic the Hedgehog (USA)",
            regions=["USA"],
            languages=["en"],
            dump_status=DumpStatus.VERIFIED,
            naming_convention=NamingConvention.NO_INTRO,
            library_id=library_id,
        )
        session.add(release)
        await session.commit()
        release_id = release.id

    # Without force, the in-use gate fires.
    resp_no_force = await api_client.delete(
        f"/api/v3/rom/library/{library_id}"
    )
    assert resp_no_force.status_code == 409
    assert resp_no_force.json()["errorCode"] == "library_in_use"

    # With force, the library is removed and the Release.library_id is
    # set to NULL (no files on disk are touched — there are none here).
    resp = await api_client.delete(f"/api/v3/rom/library/{library_id}?force=true")
    assert resp.status_code == 204

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        gone = (
            await session.execute(
                select(Library).where(Library.id == library_id)
            )
        ).scalar_one_or_none()
        assert gone is None

        release_row = (
            await session.execute(
                select(Release).where(Release.id == release_id)
            )
        ).scalar_one()
        assert release_row.library_id is None


# ---------------------------------------------------------------------------
# Update-with-platform-ids round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_replaces_platform_ids(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_library_path: Path,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    profile_ids = await seed_profiles(api_engine)

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        p1 = Platform(name="Mega Drive", slug="megadrive")
        p2 = Platform(name="SNES", slug="snes")
        session.add_all([p1, p2])
        await session.commit()
        await session.refresh(p1)
        await session.refresh(p2)
        platform_ids = [p1.id, p2.id]

    create = await api_client.post(
        "/api/v3/rom/library",
        json={
            **_payload(tmp_library_path=tmp_library_path, profile_ids=profile_ids),
            "platforms_restricted": True,
            "platform_ids": [platform_ids[0]],
        },
    )
    assert create.status_code == 201
    library_id = create.json()["id"]
    assert create.json()["platform_ids"] == [platform_ids[0]]

    update = await api_client.put(
        f"/api/v3/rom/library/{library_id}",
        json={"platform_ids": platform_ids},
    )
    assert update.status_code == 200
    assert sorted(update.json()["platform_ids"]) == sorted(platform_ids)


# ---------------------------------------------------------------------------
# Duplicate-name conflict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_name_returns_409(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_library_path: Path,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    profile_ids = await seed_profiles(api_engine)

    payload = _payload(
        tmp_library_path=tmp_library_path, profile_ids=profile_ids
    )
    first = await api_client.post("/api/v3/rom/library", json=payload)
    assert first.status_code == 201
    second = await api_client.post("/api/v3/rom/library", json=payload)
    assert second.status_code == 409
    assert second.json()["errorCode"] == "duplicate"
