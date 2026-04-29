"""End-to-end boot + encryption round-trip smoke test (T066, SC-006).

Boots a minimal FastAPI app, encrypts a provider config via the
admin endpoint, "restarts" by building a fresh app over the same
engine + same ``ROMARR_AUTH_SECRET_KEY``, and confirms the
provider round-trips: the encrypted blob decrypts to the original
plaintext on the second app instance.

This is the SC-006 acceptance test: encryption-at-rest survives a
process restart provided the master key is unchanged.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.api.app import create_app
from romarr.auth import ROLE_ADMIN, User, hash_password
from romarr.metadata.encryption import decrypt
from romarr.metadata.models import MetadataProviderConfig
from tests.metadata.api.conftest import seed_provider_rows


@pytest_asyncio.fixture
async def fresh_client_factory(
    api_engine: AsyncEngine,
) -> AsyncIterator[Any]:
    """Yields a callable that builds a brand-new FastAPI app + httpx
    client over the SAME engine each time it's called — simulating a
    process restart while preserving the on-disk state."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)

    clients: list[httpx.AsyncClient] = []

    async def _factory() -> httpx.AsyncClient:
        app = create_app()
        app.state.db_engine = api_engine
        app.state.db_sessionmaker = sm
        transport = ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://test")
        clients.append(client)
        return client

    yield _factory

    for c in clients:
        await c.aclose()


async def _seed_admin_and_login(
    api_engine: AsyncEngine, client: httpx.AsyncClient
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        existing = (
            await session.execute(
                select(User).where(User.username == "admin")
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                User(
                    username="admin",
                    role=ROLE_ADMIN,
                    is_active=True,
                    hashed_password=hash_password("goodpassword"),
                )
            )
            await session.commit()
    response = await client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert response.status_code == 204


async def test_provider_config_round_trips_across_app_restart(
    api_engine: AsyncEngine,
    metadata_env: Any,
    fresh_client_factory: Any,
) -> None:
    """Configure IGDB on app instance #1, then build a fresh app over
    the same DB + same secret key and assert the cipher decrypts."""
    await seed_provider_rows(api_engine)

    secret_config = {"client_id": "igdb-id-42", "client_secret": "shh-secret"}

    # ---- App instance #1: write the encrypted config via the API ----
    client_one = await fresh_client_factory()
    await _seed_admin_and_login(api_engine, client_one)
    response = await client_one.put(
        "/api/v3/metadata/provider/igdb",
        json={"enabled": True, "config": secret_config},
    )
    assert response.status_code == 200
    assert response.json()["is_configured"] is True

    # ---- "Process restart": new app, same engine, same secret key ----
    client_two = await fresh_client_factory()
    await _seed_admin_and_login(api_engine, client_two)

    # The DB blob is opaque ciphertext.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(MetadataProviderConfig).where(
                    MetadataProviderConfig.provider_name == "igdb"
                )
            )
        ).scalar_one()
    assert row.config_encrypted is not None
    assert row.config_encrypted != json.dumps(secret_config).encode()

    # And the second app instance's encryption helper round-trips it.
    plaintext = json.loads(decrypt(row.config_encrypted).decode("utf-8"))
    assert plaintext == secret_config

    # The list endpoint on app #2 reports the provider as configured.
    response = await client_two.get("/api/v3/metadata/provider/igdb")
    assert response.status_code == 200
    assert response.json()["is_configured"] is True
    assert response.json()["enabled"] is True
