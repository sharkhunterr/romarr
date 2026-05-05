"""Unidentified-dump endpoint tests (T086, T090, FR-038, slice 84)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import (
    Dump,
    Game,
    Platform,
    Release,
    UnidentifiedDump,
)
from romarr.importer.models import ImportHistory
from tests.importer.api.conftest import seed_user_and_login

_seed_counter = 0


async def _seed_unidentified(
    api_engine: AsyncEngine, *, count: int = 1, library_id: int | None = None
) -> list[int]:
    global _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    ids: list[int] = []
    async with sm() as session:
        for _ in range(count):
            _seed_counter += 1
            row = UnidentifiedDump(
                path=f"/downloads/unknown-{_seed_counter}.zip",
                size_bytes=1024 + _seed_counter,
                discovered_at=datetime.now(UTC),
                rejection_reason="match:no_game",
                library_id=library_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            ids.append(row.id)
    return ids


@pytest.mark.asyncio
async def test_list_unidentified_paginated(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    await _seed_unidentified(api_engine, count=3)

    response = await api_client.get("/api/v3/rom/unidentified")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    # Every row carries the spec-008 extension columns.
    assert all("rejection_reason" in r for r in rows)


@pytest.mark.asyncio
async def test_list_unidentified_filter_by_library(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    await _seed_unidentified(api_engine, count=2, library_id=1)
    await _seed_unidentified(api_engine, count=3, library_id=2)

    response = await api_client.get(
        "/api/v3/rom/unidentified?library_id=2"
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    assert all(r["library_id"] == 2 for r in rows)


@pytest.mark.asyncio
async def test_delete_unidentified_succeeds(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    [target_id] = await _seed_unidentified(api_engine, count=1)

    response = await api_client.delete(
        f"/api/v3/rom/unidentified/{target_id}"
    )
    assert response.status_code == 204

    # The DB row is gone.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        gone = (
            await session.execute(
                select(UnidentifiedDump).where(
                    UnidentifiedDump.id == target_id
                )
            )
        ).scalar_one_or_none()
        assert gone is None


@pytest.mark.asyncio
async def test_delete_unidentified_404_when_missing(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    response = await api_client.delete("/api/v3/rom/unidentified/9999")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "not_found"


@pytest.mark.asyncio
async def test_delete_unidentified_user_role_forbidden(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    [target_id] = await _seed_unidentified(api_engine, count=1)

    response = await api_client.delete(
        f"/api/v3/rom/unidentified/{target_id}"
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_unidentified_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/rom/unidentified")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_unidentified_keeps_source_file(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """Spec 008 T086 / FR-038: DELETE on an unidentified row removes
    the DB row but MUST NOT touch the source file on disk. Operators
    rely on the file staying around so they can re-trigger the
    pipeline against the same byte stream after fixing whatever
    config gap caused the original park.
    """
    await seed_user_and_login(api_engine, api_client, role="admin")

    # Real on-disk file the unidentified row points at.
    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(b"\x00" * 4096)
    assert rom.exists()

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = UnidentifiedDump(
            path=str(rom),
            size_bytes=4096,
            discovered_at=datetime.now(UTC),
            rejection_reason="match:no_game",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        target_id = row.id

    response = await api_client.delete(
        f"/api/v3/rom/unidentified/{target_id}"
    )
    assert response.status_code == 204

    # The DB row is gone — the source file is NOT.
    async with sm() as session:
        gone = (
            await session.execute(
                select(UnidentifiedDump).where(
                    UnidentifiedDump.id == target_id
                )
            )
        ).scalar_one_or_none()
        assert gone is None
    assert rom.exists(), "source file must survive the DELETE per FR-038"


# ---------------------------------------------------------------------------
# POST /unidentified/{id}/match (slice 84)


_chain_counter = 0


async def _seed_release_chain(
    api_engine: AsyncEngine,
) -> tuple[int, int]:
    """Seed Platform → Game → Release. Returns (game_id, release_id).
    Each call uses a unique slug suffix so the same test can seed
    two independent chains for cross-game scenarios."""
    global _chain_counter
    _chain_counter += 1
    suffix = _chain_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(
            slug=f"megadrive-match-{suffix}", name="Mega Drive"
        )
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"sonic-match-{suffix}",
            title="Sonic the Hedgehog",
        )
        session.add(game)
        await session.flush()
        release = Release(
            game_id=game.id,
            name=f"Sonic the Hedgehog (USA){suffix}",
        )
        session.add(release)
        await session.commit()
        await session.refresh(game)
        await session.refresh(release)
        return game.id, release.id


async def _seed_unidentified_with_file(
    api_engine: AsyncEngine, *, tmp_path: Path, payload: bytes
) -> int:
    """Seed an UnidentifiedDump pointing at a real file we wrote
    so manual_import_known can re-hash it on demand."""
    src = tmp_path / "dl" / "rom.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(payload)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = UnidentifiedDump(
            path=str(src),
            size_bytes=len(payload),
            discovered_at=datetime.now(UTC),
            sha1=hashlib.sha1(payload).hexdigest(),
            crc32="d3578bf6",
            md5="0" * 32,
            rejection_reason="match:no_game",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_match_unidentified_inserts_dump_and_drops_unidentified(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    game_id, release_id = await _seed_release_chain(api_engine)
    target_id = await _seed_unidentified_with_file(
        api_engine, tmp_path=tmp_path, payload=b"x" * 1024
    )

    response = await api_client.post(
        f"/api/v3/rom/unidentified/{target_id}/match",
        json={"game_id": game_id, "release_id": release_id},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["success"] is True
    assert body["coalesced"] is False
    assert body["game_id"] == game_id
    assert body["release_id"] == release_id
    assert body["dump_id"] is not None
    assert body["imported_via"] == "manual"
    assert body["imported_by"] == "admin-user"

    # Dump persisted, Release transitioned, UnidentifiedDump dropped.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        dump = (
            await session.execute(
                select(Dump).where(Dump.id == body["dump_id"])
            )
        ).scalar_one()
        assert dump.release_id == release_id
        rel = (
            await session.execute(
                select(Release).where(Release.id == release_id)
            )
        ).scalar_one()
        assert rel.status == "imported"
        gone = (
            await session.execute(
                select(UnidentifiedDump).where(UnidentifiedDump.id == target_id)
            )
        ).scalar_one_or_none()
        assert gone is None

        # ImportHistory row exists for the audit trail.
        history = (
            await session.execute(
                select(ImportHistory).where(ImportHistory.id == body["id"])
            )
        ).scalar_one()
        assert history.success is True
        assert history.coalesced is False


@pytest.mark.asyncio
async def test_match_unidentified_404_when_entry_missing(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    game_id, release_id = await _seed_release_chain(api_engine)
    response = await api_client.post(
        "/api/v3/rom/unidentified/9999/match",
        json={"game_id": game_id, "release_id": release_id},
    )
    assert response.status_code == 404
    assert response.json()["errorCode"] == "not_found"


@pytest.mark.asyncio
async def test_match_unidentified_422_when_release_id_missing(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """Manual match requires the operator to pick a Release —
    falling back to "the Game's first wanted Release" would be
    ambiguous, so the API rejects."""
    await seed_user_and_login(api_engine, api_client, role="admin")
    game_id, _ = await _seed_release_chain(api_engine)
    target_id = await _seed_unidentified_with_file(
        api_engine, tmp_path=tmp_path, payload=b"x" * 64
    )
    response = await api_client.post(
        f"/api/v3/rom/unidentified/{target_id}/match",
        json={"game_id": game_id},
    )
    assert response.status_code == 422
    assert response.json()["errorCode"] == "release_id_required"


@pytest.mark.asyncio
async def test_match_unidentified_409_on_release_game_mismatch(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """Operator named game X but provided release that belongs to
    game Y — bail with 409 rather than persist the cross-binding."""
    await seed_user_and_login(api_engine, api_client, role="admin")
    game_a, release_a = await _seed_release_chain(api_engine)
    _, release_b = await _seed_release_chain(api_engine)  # different game
    target_id = await _seed_unidentified_with_file(
        api_engine, tmp_path=tmp_path, payload=b"x" * 64
    )

    response = await api_client.post(
        f"/api/v3/rom/unidentified/{target_id}/match",
        json={"game_id": game_a, "release_id": release_b},
    )
    assert response.status_code == 409
    assert response.json()["errorCode"] == "release_game_mismatch"


@pytest.mark.asyncio
async def test_match_unidentified_user_role_forbidden(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """CL005 — admin-only mutating endpoint."""
    await seed_user_and_login(api_engine, api_client, role="user")
    game_id, release_id = await _seed_release_chain(api_engine)
    target_id = await _seed_unidentified_with_file(
        api_engine, tmp_path=tmp_path, payload=b"x" * 64
    )

    response = await api_client.post(
        f"/api/v3/rom/unidentified/{target_id}/match",
        json={"game_id": game_id, "release_id": release_id},
    )
    assert response.status_code == 403
