"""Health refresh endpoint tests (T066, FR-024b)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
    User,
    hash_password,
)


async def _seed_user(
    engine: AsyncEngine,
    *,
    username: str,
    role: str,
) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username=username,
                role=role,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_unauthenticated_refresh_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post("/api/v3/health/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_readonly_refresh_returns_403(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="reader", role=ROLE_READONLY)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "reader", "password": "goodpassword"},
    )
    response = await api_client.post("/api/v3/health/refresh")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_refresh_returns_403(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A regular user (non-admin) cannot trigger refresh — the
    endpoint fires outbound HTTP probes (SSRF surface)."""
    await _seed_user(api_engine, username="bob", role=ROLE_USER)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "bob", "password": "goodpassword"},
    )
    response = await api_client.post("/api/v3/health/refresh")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_refresh_returns_200(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """An admin can refresh. With no engine wired into the app
    yet, the endpoint falls back to the persisted snapshot —
    still HTTP 200."""
    await _seed_user(api_engine, username="alice", role=ROLE_ADMIN)
    await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    response = await api_client.post("/api/v3/health/refresh")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "by_category" in body
