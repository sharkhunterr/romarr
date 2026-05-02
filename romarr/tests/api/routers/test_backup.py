"""Backup router tests (T040, T041 partial, FR-014).

T040 (list_backups) and the DELETE endpoint are covered here.
T041 (manual trigger) is served by the unified command bus
(POST /api/v3/command {"name": "Backup"}); pinned in
tests/tasks/api/test_command_endpoint.py rather than duplicated
here.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from romarr.config import get_settings
from tests.api.test_auth_endpoints import _seed_admin_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backup_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Point ``Settings.backup_path`` at a fresh tmp dir."""
    monkeypatch.setenv("ROMARR_BACKUP_PATH", str(tmp_path))
    get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        get_settings.cache_clear()


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
# T040 — GET /api/v3/system/backup lists backup files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_backups_empty_dir(
    authed_client: httpx.AsyncClient, backup_dir: Path
) -> None:
    """Empty backup_path returns ``[]``."""
    resp = await authed_client.get("/api/v3/system/backup")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_backups_missing_dir_returns_empty(
    authed_client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``backup_path`` may not exist on a fresh install — return
    ``[]`` rather than crashing."""
    missing = tmp_path / "absent"
    monkeypatch.setenv("ROMARR_BACKUP_PATH", str(missing))
    get_settings.cache_clear()
    try:
        resp = await authed_client.get("/api/v3/system/backup")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_list_backups_returns_metadata_sorted_newest_first(
    authed_client: httpx.AsyncClient, backup_dir: Path
) -> None:
    """Each entry carries filename / lastWriteTime / size.
    Sorted newest-first — the operator UI wants the latest at
    the top."""
    import os
    import time

    early = backup_dir / "romarr_backup_2025-01-01.zip"
    early.write_bytes(b"old")
    # Force a different mtime so the newest-first sort is
    # observable even on filesystems with coarse timestamps.
    os.utime(early, (time.time() - 3600, time.time() - 3600))

    recent = backup_dir / "romarr_backup_2026-04-30.zip"
    recent.write_bytes(b"newer-content")

    resp = await authed_client.get("/api/v3/system/backup")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["filename"] == "romarr_backup_2026-04-30.zip"
    assert body[1]["filename"] == "romarr_backup_2025-01-01.zip"
    assert body[0]["size"] == len(b"newer-content")
    assert "lastWriteTime" in body[0]


# ---------------------------------------------------------------------------
# DELETE /api/v3/system/backup/{filename}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_backup_removes_file(
    authed_client: httpx.AsyncClient, backup_dir: Path
) -> None:
    target = backup_dir / "romarr_backup_2026-04-30.zip"
    target.write_bytes(b"content")

    resp = await authed_client.delete(
        f"/api/v3/system/backup/{target.name}"
    )
    assert resp.status_code == 204
    assert not target.exists()


@pytest.mark.asyncio
async def test_delete_unknown_backup_returns_404(
    authed_client: httpx.AsyncClient, backup_dir: Path
) -> None:
    resp = await authed_client.delete(
        "/api/v3/system/backup/missing.zip"
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "not_found"


def test_safe_backup_path_rejects_traversal_directly(
    backup_dir: Path,
) -> None:
    """Defense-in-depth unit test on the path resolver."""
    from fastapi import HTTPException

    from romarr.api.routers.backup import _safe_backup_path

    for sketchy in (
        "../etc/passwd",
        "..\\windows\\system32",
        ".env",
    ):
        with pytest.raises(HTTPException) as exc_info:
            _safe_backup_path(sketchy)
        assert exc_info.value.status_code == 400
        assert (
            exc_info.value.detail["errorCode"]  # type: ignore[index,call-overload]
            == "invalid_backup_filename"
        )


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_requires_auth(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/system/backup")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_requires_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A readonly principal can't delete backups."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from romarr.auth import ROLE_READONLY, User, hash_password

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="reader",
                role=ROLE_READONLY,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()

    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "reader", "password": "goodpassword"},
    )
    assert login.status_code == 204

    resp = await api_client.delete(
        "/api/v3/system/backup/anything.zip"
    )
    assert resp.status_code == 403
