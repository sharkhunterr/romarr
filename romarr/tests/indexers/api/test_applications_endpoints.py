"""Application registration endpoint tests (T049-T051)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth.hashing import verify_api_key
from romarr.auth.models import ApiKey
from romarr.indexers.models import Application
from tests.indexers.api.conftest import seed_admin_and_login

_VALID_PAYLOAD = {
    "name": "Prowlarr Prod",
    "sync_level": "full_sync",
    "prowlarr_url": "https://prowlarr.test",
    "prowlarr_api_key": "prowlarr-secret",
}


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/applications", json=_VALID_PAYLOAD
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_returns_token_once(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T049: POST returns app_token in plaintext exactly once;
    subsequent reads omit it."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/applications", json=_VALID_PAYLOAD
    )
    assert response.status_code == 201
    body = response.json()
    assert body["app_token"] is not None
    plaintext_token = body["app_token"]
    app_id = body["id"]

    # Post-rework, the application's ``app_token`` IS a real Romarr
    # API key (the custom token design didn't survive contact with
    # Prowlarr's Sonarr-compat client). ``Application.app_token_hash``
    # stores a pointer ``apikey:{id}`` to the minted api_key row, not
    # a hash; the BLAKE2b digest lives on that api_key row, and the
    # plaintext is NEVER persisted.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(Application).where(Application.id == app_id)
            )
        ).scalar_one()
        assert row.app_token_hash.startswith("apikey:")
        api_key_id = int(row.app_token_hash.removeprefix("apikey:"))
        api_key_row = (
            await session.execute(
                select(ApiKey).where(ApiKey.id == api_key_id)
            )
        ).scalar_one()

    assert verify_api_key(plaintext_token, api_key_row.key_hash) is True
    # No bytewise leak of the plaintext.
    assert plaintext_token not in row.app_token_hash
    assert plaintext_token != api_key_row.key_hash

    # GET on the same id returns ApplicationRead (no app_token field).
    read_response = await api_client.get(f"/api/v3/applications/{app_id}")
    assert read_response.status_code == 200
    assert "app_token" not in read_response.json()


@pytest.mark.asyncio
async def test_duplicate_url_returns_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T050: a second registration with the same prowlarr_url → HTTP 409."""
    await seed_admin_and_login(api_engine, api_client)
    first = await api_client.post("/api/v3/applications", json=_VALID_PAYLOAD)
    assert first.status_code == 201

    second = await api_client.post("/api/v3/applications", json=_VALID_PAYLOAD)
    assert second.status_code == 409
    assert second.json()["errorCode"] == "duplicate"


@pytest.mark.asyncio
async def test_delete_unregisters(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T051: DELETE drops the application; subsequent inbound calls
    bearing its token would be rejected because the token hash is
    gone (we verify by checking the row is removed)."""
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post(
        "/api/v3/applications", json=_VALID_PAYLOAD
    )
    app_id = create.json()["id"]

    delete = await api_client.delete(f"/api/v3/applications/{app_id}")
    assert delete.status_code == 204

    # Row is gone.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(Application).where(Application.id == app_id)
            )
        ).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_list_returns_registered(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    await api_client.post("/api/v3/applications", json=_VALID_PAYLOAD)
    await api_client.post(
        "/api/v3/applications",
        json={**_VALID_PAYLOAD, "prowlarr_url": "https://prowlarr-2.test"},
    )

    response = await api_client.get("/api/v3/applications")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    # Every list row drops the plaintext token.
    assert all("app_token" not in r for r in rows)


@pytest.mark.asyncio
async def test_read_unknown_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.get("/api/v3/applications/9999")
    assert response.status_code == 404
