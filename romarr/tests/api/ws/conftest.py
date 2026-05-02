"""Shared fixtures for WS tests.

Both the auth tests and the message-coverage tests need:
  * an admin User + API key seeded into the engine;
  * a TestClient over a fresh app pointed at that engine,
    NOT entered as a context manager (the lifespan would
    overwrite ``app.state.db_sessionmaker`` with a fresh
    engine that has no tables).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.api import create_app
from romarr.auth import ROLE_ADMIN, User, hash_api_key, hash_password
from romarr.auth.models import ApiKey


async def _seed_admin_with_api_key(
    engine: AsyncEngine, *, username: str = "ws-admin"
) -> str:
    """Insert an admin user + API key. Returns the plaintext."""
    plaintext = f"rmk_{username}_test"
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        user = User(
            username=username,
            role=ROLE_ADMIN,
            is_active=True,
            hashed_password=hash_password("goodpassword"),
        )
        session.add(user)
        await session.flush()
        session.add(
            ApiKey(
                user_id=user.id,
                name="ws-test",
                key_prefix=plaintext[:8],
                key_hash=hash_api_key(plaintext),
                scopes=["read"],
            )
        )
        await session.commit()
    return plaintext


def _build_sync_client(engine: AsyncEngine) -> TestClient:
    """Build a fresh app + sync TestClient over the test
    engine. Returns the TestClient WITHOUT entering its
    context manager — that would fire the lifespan, which
    builds its own fresh engine on app.state and overwrites
    the one we just stamped. ``websocket_connect`` doesn't
    need lifespan to be active; the sessionmaker stays as we
    set it."""
    app = create_app()
    sm = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_engine = engine
    app.state.db_sessionmaker = sm
    return TestClient(app)


@pytest_asyncio.fixture
async def authed_ws_client(
    api_engine: AsyncEngine,
) -> AsyncIterator[tuple[TestClient, str]]:
    """Yields (client, apikey_plaintext) for tests that need a
    pre-seeded auth context. Client is NOT entered as a
    context manager — see _build_sync_client for rationale."""
    plaintext = await _seed_admin_with_api_key(api_engine)
    client = _build_sync_client(api_engine)
    yield client, plaintext
