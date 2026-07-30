"""End-to-end API tests for /api/v3/community/*."""

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
async def test_list_sources_empty_returns_200(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Regression: GET /api/v3/community/source must not 500 on
    an empty table (initial state — no sources ever added)."""
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.get("/api/v3/community/source")
    assert r.status_code == 200, r.text
    assert r.json() == []


@pytest.mark.asyncio
async def test_updates_feed_empty_state(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Regression: GET /api/v3/community/updates must not 500 when
    the community table is empty and only the Romarr GitHub check
    contributes to the feed."""
    await _seed_admin_and_login(api_engine, api_client)
    r = await api_client.get("/api/v3/community/updates")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "romarr" in body
    assert body["sources"] == []
    assert body["total_updates"] >= 0
