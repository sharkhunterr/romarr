"""Endpoint tests — /api/v3/rom/platform-pack-source/*.

Cover CRUD + auth-gating. Sync-now is exercised via the fetcher
unit tests and would require a full ingestor stub for e2e — kept
out of scope here.
"""
from __future__ import annotations

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
async def test_list_requires_admin(api_client: httpx.AsyncClient) -> None:
    r = await api_client.get("/api/v3/rom/platform-pack-source")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_auto_detects_kind_from_url(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)

    # Directory URL → github_dir
    r = await api_client.post(
        "/api/v3/rom/platform-pack-source",
        json={
            "name": "Community Dir",
            "url": "https://github.com/o/r/tree/main/packs",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "github_dir"

    # Raw YAML URL → raw
    r = await api_client.post(
        "/api/v3/rom/platform-pack-source",
        json={
            "name": "Community Raw",
            "url": "https://raw.githubusercontent.com/o/r/main/pack.yaml",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "raw"


@pytest.mark.asyncio
async def test_duplicate_name_rejected_with_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    payload = {
        "name": "Dup",
        "url": "https://raw.example.com/pack.yaml",
    }
    r = await api_client.post("/api/v3/rom/platform-pack-source", json=payload)
    assert r.status_code == 201
    r2 = await api_client.post("/api/v3/rom/platform-pack-source", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_patch_toggles_enabled(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.post(
        "/api/v3/rom/platform-pack-source",
        json={"name": "Src", "url": "https://raw.example.com/pack.yaml"},
    )
    sid = r.json()["id"]
    r = await api_client.patch(
        f"/api/v3/rom/platform-pack-source/{sid}", json={"enabled": False}
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


@pytest.mark.asyncio
async def test_delete_returns_204_and_removes(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.post(
        "/api/v3/rom/platform-pack-source",
        json={"name": "Byebye", "url": "https://raw.example.com/pack.yaml"},
    )
    sid = r.json()["id"]
    r = await api_client.delete(f"/api/v3/rom/platform-pack-source/{sid}")
    assert r.status_code == 204
    r = await api_client.get("/api/v3/rom/platform-pack-source")
    assert all(s["id"] != sid for s in r.json())


@pytest.mark.asyncio
async def test_sync_on_disabled_source_returns_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.post(
        "/api/v3/rom/platform-pack-source",
        json={"name": "Src", "url": "https://raw.example.com/pack.yaml"},
    )
    sid = r.json()["id"]
    await api_client.patch(
        f"/api/v3/rom/platform-pack-source/{sid}", json={"enabled": False}
    )
    r = await api_client.post(f"/api/v3/rom/platform-pack-source/{sid}/sync")
    assert r.status_code == 409
