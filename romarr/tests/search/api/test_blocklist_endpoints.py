"""Blocklist endpoint tests (T067)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.search.api.conftest import seed_admin_and_login


@pytest.mark.asyncio
async def test_full_crud_round_trip(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)

    create = await api_client.post(
        "/api/v3/blocklist",
        json={
            "release_title": "Bad Release",
            "reason": "manual",
            "hash_sha1": "a" * 40,
        },
    )
    assert create.status_code == 201
    entry_id = create.json()["id"]

    listing = await api_client.get("/api/v3/blocklist")
    assert listing.status_code == 200
    assert any(r["id"] == entry_id for r in listing.json())

    delete = await api_client.delete(f"/api/v3/blocklist/{entry_id}")
    assert delete.status_code == 204

    after = await api_client.get("/api/v3/blocklist")
    assert all(r["id"] != entry_id for r in after.json())


@pytest.mark.asyncio
async def test_post_at_least_one_match_field_validator(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """FR-021: a blocklist row with no match field is rejected at save."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/blocklist",
        json={
            "release_title": "Anything",
            "reason": "manual",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_unknown_returns_404(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.delete("/api/v3/blocklist/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/blocklist")
    assert response.status_code == 401
