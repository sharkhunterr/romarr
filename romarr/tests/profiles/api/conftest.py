"""Module-local fixtures for the profiles API tests."""

from __future__ import annotations

from typing import Any, Literal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_USER, User, hash_password
from romarr.config.settings import get_settings


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def seed_user_and_login(
    api_engine: AsyncEngine,
    api_client: httpx.AsyncClient,
    *,
    role: Literal["admin", "user"] = "admin",
) -> None:
    """Seed a user with the requested role + log in via the auth router."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    role_value = ROLE_ADMIN if role == "admin" else ROLE_USER
    async with sm() as session:
        session.add(
            User(
                username=f"{role}-user",
                role=role_value,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": f"{role}-user", "password": "goodpassword"},
    )
    assert response.status_code == 204
