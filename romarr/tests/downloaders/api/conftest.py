"""Module-local fixtures for download-client API tests."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password
from romarr.config.settings import get_settings


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Stable encryption key for the password / api_key Fernet helpers."""
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def seed_admin_and_login(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    """Seed an admin user + log in via the auth router."""
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
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert response.status_code == 204
