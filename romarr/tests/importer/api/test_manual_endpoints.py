"""Manual import + retry endpoint tests (spec 008 T088)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_USER, User, hash_password
from romarr.importer.models import ImportHistory


async def _seed_user(api_engine: AsyncEngine, *, role: str) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username=f"{role}-user",
                role=role,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()


async def _login(client: httpx.AsyncClient, role: str) -> None:
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": f"{role}-user", "password": "goodpassword"},
    )
    assert response.status_code == 204


def _wire_sessionmaker(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> async_sessionmaker:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    api_client._transport.app.state.db_sessionmaker = sm  # type: ignore[attr-defined]
    return sm


async def _seed_failed_history(
    api_engine: AsyncEngine, *, source_path: str
) -> int:
    """Insert a failed ImportHistory row pointing at ``source_path``.
    Returns the row id."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = ImportHistory(
            source_path=source_path,
            imported_via="manual",
            success=False,
            error_msg="match:no_game",
            correlation_id=str(uuid4()),
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            duration_ms=10,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_post_manual_returns_history_per_entry(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """T088 — POST ``/api/v3/rom/import/manual`` runs each entry
    and returns one ImportHistoryRead per entry."""
    await _seed_user(api_engine, role=ROLE_ADMIN)
    sm = _wire_sessionmaker(api_client, api_engine)

    # Need at least one Game/Release for the entry's game_id ref.
    from romarr.domain.models import Game, Platform, Release
    from romarr.domain.enums import DumpStatus, NamingConvention

    async with sm() as session:
        platform = Platform(slug="megadrive-mt88", name="Mega Drive")
        session.add(platform)
        await session.commit()
        await session.refresh(platform)
        game = Game(
            platform_id=platform.id, slug="game-mt88", title="Sonic"
        )
        session.add(game)
        await session.commit()
        await session.refresh(game)
        release = Release(
            game_id=game.id,
            name="Sonic (USA)",
            regions=["USA"],
            languages=["en"],
            dump_status=DumpStatus.VERIFIED,
            naming_convention=NamingConvention.NO_INTRO,
            status="wanted",
        )
        session.add(release)
        await session.commit()
        await session.refresh(release)

    rom = tmp_path / "rom.md"
    rom.write_bytes(b"\x00" * 256)

    await _login(api_client, ROLE_ADMIN)
    response = await api_client.post(
        "/api/v3/rom/import/manual",
        json={
            "entries": [
                {
                    "path": str(rom),
                    "game_id": game.id,
                    "release_id": release.id,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert isinstance(body[0]["id"], int)
    assert body[0]["imported_via"] == "manual"


@pytest.mark.asyncio
async def test_post_manual_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    rom = tmp_path / "rom.md"
    rom.write_bytes(b"\x00" * 256)
    response = await api_client.post(
        "/api/v3/rom/import/manual",
        json={"entries": [{"path": str(rom), "game_id": 1}]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_manual_user_role_returns_403(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """User-role principals are blocked — admin only (FR-033a)."""
    await _seed_user(api_engine, role=ROLE_USER)
    _wire_sessionmaker(api_client, api_engine)

    rom = tmp_path / "rom.md"
    rom.write_bytes(b"\x00" * 256)
    await _login(api_client, ROLE_USER)
    response = await api_client.post(
        "/api/v3/rom/import/manual",
        json={"entries": [{"path": str(rom), "game_id": 1}]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_post_manual_empty_entries_returns_422(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """``entries`` must be non-empty per the schema's
    ``min_length=1`` constraint."""
    await _seed_user(api_engine, role=ROLE_ADMIN)
    _wire_sessionmaker(api_client, api_engine)
    await _login(api_client, ROLE_ADMIN)
    response = await api_client.post(
        "/api/v3/rom/import/manual", json={"entries": []}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_retry_creates_new_history_row(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """T088 — POST /api/v3/rom/import/retry/{id} replays the
    original source path with a fresh correlation id; original
    row preserved (FR-035)."""
    await _seed_user(api_engine, role=ROLE_ADMIN)
    _wire_sessionmaker(api_client, api_engine)

    rom = tmp_path / "rom.md"
    rom.write_bytes(b"\x00" * 256)
    original_id = await _seed_failed_history(api_engine, source_path=str(rom))

    await _login(api_client, ROLE_ADMIN)
    response = await api_client.post(
        f"/api/v3/rom/import/retry/{original_id}"
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "history" in body
    assert body["history"]["id"] != original_id
    assert body["history"]["imported_via"] == "manual"

    # Both rows still exist — retry is non-destructive.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (
            await session.execute(
                select(ImportHistory).where(
                    ImportHistory.source_path == str(rom)
                )
            )
        ).scalars().all()
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_post_retry_unknown_id_returns_404(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    await _seed_user(api_engine, role=ROLE_ADMIN)
    _wire_sessionmaker(api_client, api_engine)
    await _login(api_client, ROLE_ADMIN)
    response = await api_client.post("/api/v3/rom/import/retry/99999")
    assert response.status_code == 404
    body = response.json()
    detail = body.get("detail")
    if isinstance(detail, dict):
        assert detail["errorCode"] == "import_history_not_found"
    else:
        assert body.get("errorCode") == "import_history_not_found"


@pytest.mark.asyncio
async def test_post_retry_unauthenticated_returns_401(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    response = await api_client.post("/api/v3/rom/import/retry/1")
    assert response.status_code == 401
