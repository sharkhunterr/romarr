"""/api/v3/metadata/provider* endpoint tests (T056)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_USER, User, hash_password
from romarr.metadata.encryption import decrypt
from romarr.metadata.models import MetadataProviderConfig
from tests.metadata.api.conftest import seed_provider_rows


async def _seed_user(
    engine: AsyncEngine, *, username: str, role: str
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


async def _login_admin(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    await _seed_user(api_engine, username="admin", role=ROLE_ADMIN)
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/metadata/provider")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_returns_403(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_user(api_engine, username="alice", role=ROLE_USER)
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert response.status_code == 204

    response = await api_client.get("/api/v3/metadata/provider")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_lists_seeded_providers(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await seed_provider_rows(api_engine)
    await _login_admin(api_engine, api_client)

    response = await api_client.get("/api/v3/metadata/provider")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 9
    names = [r["provider_name"] for r in rows]
    # Ordered by priority_global ASC.
    assert names[0] == "igdb"
    assert all(r["enabled"] is False for r in rows)
    assert all(r["is_configured"] is False for r in rows)


@pytest.mark.asyncio
async def test_read_unknown_provider_404(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await seed_provider_rows(api_engine)
    await _login_admin(api_engine, api_client)

    response = await api_client.get("/api/v3/metadata/provider/imaginary")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "unknown_provider"


@pytest.mark.asyncio
async def test_update_toggles_enabled_and_encrypts_config(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await seed_provider_rows(api_engine)
    await _login_admin(api_engine, api_client)

    response = await api_client.put(
        "/api/v3/metadata/provider/igdb",
        json={
            "enabled": True,
            "config": {"client_id": "abc", "client_secret": "shh"},
            "rate_limit_rps": 8,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["is_configured"] is True
    assert body["rate_limit_rps"] == 8

    # The persisted blob is the Fernet token wrapping the JSON config.
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
    plaintext = json.loads(decrypt(row.config_encrypted).decode("utf-8"))
    assert plaintext == {"client_id": "abc", "client_secret": "shh"}


@pytest.mark.asyncio
async def test_update_validation_rejects_bad_rps(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await seed_provider_rows(api_engine)
    await _login_admin(api_engine, api_client)

    response = await api_client.put(
        "/api/v3/metadata/provider/igdb",
        json={"rate_limit_rps": 0},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_endpoint_requires_configured_provider(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await seed_provider_rows(api_engine)
    await _login_admin(api_engine, api_client)

    response = await api_client.post("/api/v3/metadata/provider/igdb/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "not_configured"


@pytest.mark.asyncio
async def test_test_endpoint_for_unimplemented_provider(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    """Every named provider now has a class registered, so the
    'provider_not_implemented' branch only fires for an unknown name —
    which the seed step doesn't include. Simulate the branch by
    temporarily clearing the registry entry inside the test."""
    from romarr.metadata import PROVIDER_REGISTRY

    await seed_provider_rows(api_engine)
    await _login_admin(api_engine, api_client)

    saved = PROVIDER_REGISTRY.pop("launchbox", None)
    try:
        response = await api_client.post(
            "/api/v3/metadata/provider/launchbox/test"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["error"] == "provider_not_implemented"
    finally:
        if saved is not None:
            PROVIDER_REGISTRY["launchbox"] = saved
