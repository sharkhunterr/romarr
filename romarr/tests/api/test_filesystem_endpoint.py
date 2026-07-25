"""Tests for /api/v3/system/filesystem."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password


async def _seed_admin_and_login(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="admin",
                role=ROLE_ADMIN,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()
    r = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_requires_admin(api_client: httpx.AsyncClient) -> None:
    r = await api_client.get("/api/v3/system/filesystem?path=/tmp")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_root_returns_curated_mounts(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.get("/api/v3/system/filesystem")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "/"
    assert body["parent"] is None
    # /home always exists on any Linux CI runner.
    paths = {e["path"] for e in body["entries"]}
    assert "/home" in paths


@pytest.mark.asyncio
async def test_listing_a_real_dir_returns_children(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pytest's tmp_path usually lives under /tmp, which the endpoint
    # forbids by default — temporarily drop /tmp from the block list.
    from romarr.api.routers import filesystem as fs

    monkeypatch.setattr(
        fs,
        "_FORBIDDEN_PREFIXES",
        tuple(p for p in fs._FORBIDDEN_PREFIXES if p != "/tmp"),
    )

    (tmp_path / "roms").mkdir()
    (tmp_path / "downloads").mkdir()
    (tmp_path / ".hidden").mkdir()  # hidden entries filtered
    (tmp_path / "note.txt").write_text("skip me")  # files filtered

    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.get(
        f"/api/v3/system/filesystem?path={tmp_path}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == str(tmp_path)
    assert body["parent"] == str(tmp_path.parent)
    names = [e["name"] for e in body["entries"]]
    assert names == ["downloads", "roms"]  # sorted, no hidden, no file


@pytest.mark.asyncio
async def test_forbidden_prefix_rejected(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.get("/api/v3/system/filesystem?path=/proc")
    assert r.status_code == 403
    r = await api_client.get("/api/v3/system/filesystem?path=/etc/nginx")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_nonexistent_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.get(
        "/api/v3/system/filesystem?path=/data/roms/nope-never"
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_file_path_returns_400_not_dir(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from romarr.api.routers import filesystem as fs

    monkeypatch.setattr(
        fs,
        "_FORBIDDEN_PREFIXES",
        tuple(p for p in fs._FORBIDDEN_PREFIXES if p != "/tmp"),
    )

    file = tmp_path / "not-a-dir.txt"
    file.write_text("hi")

    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.get(f"/api/v3/system/filesystem?path={file}")
    assert r.status_code == 400
