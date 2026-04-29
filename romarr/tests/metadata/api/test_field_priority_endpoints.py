"""/api/v3/metadata/field-priority endpoint tests (T057)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password
from romarr.metadata.models import FieldPriority


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
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert response.status_code == 204


async def _seed_priority(
    api_engine: AsyncEngine, rows: list[tuple[str, int, str]]
) -> None:
    """Seed (field_name, priority_order, provider_name) triples."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sm() as session:
        for field, order, provider in rows:
            session.add(
                FieldPriority(
                    field_name=field,
                    provider_name=provider,
                    priority_order=order,
                    updated_at=now,
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_list_groups_by_field_in_priority_order(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await _seed_priority(
        api_engine,
        [
            ("title", 1, "igdb"),
            ("title", 2, "screenscraper"),
            ("summary", 1, "igdb"),
            ("summary", 2, "mobygames"),
        ],
    )
    await _seed_admin_and_login(api_engine, api_client)

    response = await api_client.get("/api/v3/metadata/field-priority")
    assert response.status_code == 200
    payload = response.json()

    by_field = {entry["field_name"]: entry["providers"] for entry in payload}
    assert by_field["title"] == ["igdb", "screenscraper"]
    assert by_field["summary"] == ["igdb", "mobygames"]


@pytest.mark.asyncio
async def test_update_replaces_ordering_atomically(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await _seed_priority(
        api_engine,
        [
            ("title", 1, "igdb"),
            ("title", 2, "screenscraper"),
            ("title", 3, "mobygames"),
        ],
    )
    await _seed_admin_and_login(api_engine, api_client)

    response = await api_client.put(
        "/api/v3/metadata/field-priority/title",
        json={"providers": ["mobygames", "igdb"]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "field_name": "title",
        "providers": ["mobygames", "igdb"],
    }

    # Re-read: the PUT replaced the entry; screenscraper is gone.
    list_response = await api_client.get("/api/v3/metadata/field-priority")
    by_field = {e["field_name"]: e["providers"] for e in list_response.json()}
    assert by_field["title"] == ["mobygames", "igdb"]


@pytest.mark.asyncio
async def test_update_rejects_unknown_provider(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    response = await api_client.put(
        "/api/v3/metadata/field-priority/title",
        json={"providers": ["nope"]},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "validation_failed"


@pytest.mark.asyncio
async def test_update_rejects_duplicate_provider(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    response = await api_client.put(
        "/api/v3/metadata/field-priority/title",
        json={"providers": ["igdb", "igdb"]},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_rejects_empty_providers(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    response = await api_client.put(
        "/api/v3/metadata/field-priority/title",
        json={"providers": []},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/metadata/field-priority")
    assert response.status_code == 401
