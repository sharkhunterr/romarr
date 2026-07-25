"""Tests for /api/v3/rom/platform-pack-config."""
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
async def test_get_returns_defaults_on_first_read(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.get("/api/v3/rom/platform-pack-config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["builtin_enabled"] is True
    assert body["priority"] == "community"


@pytest.mark.asyncio
async def test_patch_updates_only_provided_fields(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    # Flip both.
    r = await api_client.patch(
        "/api/v3/rom/platform-pack-config",
        json={"builtin_enabled": False, "priority": "builtin"},
    )
    assert r.status_code == 200
    assert r.json() == {"builtin_enabled": False, "priority": "builtin"}

    # Patch just one — the other stays.
    r = await api_client.patch(
        "/api/v3/rom/platform-pack-config",
        json={"builtin_enabled": True},
    )
    assert r.json() == {"builtin_enabled": True, "priority": "builtin"}


@pytest.mark.asyncio
async def test_patch_rejects_bad_priority(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.patch(
        "/api/v3/rom/platform-pack-config",
        json={"priority": "whatever"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_requires_admin(api_client: httpx.AsyncClient) -> None:
    r = await api_client.patch(
        "/api/v3/rom/platform-pack-config",
        json={"builtin_enabled": False},
    )
    assert r.status_code == 401
