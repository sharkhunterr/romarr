"""Module-local fixtures for platform-pack API tests."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password


async def seed_admin_and_login(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    """Seed an admin user and log in via the cookie-based forms-login flow."""
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
