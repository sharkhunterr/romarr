"""Unidentified-dump endpoint tests (T086, T090, FR-038)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import UnidentifiedDump
from tests.importer.api.conftest import seed_user_and_login


_seed_counter = 0


async def _seed_unidentified(
    api_engine: AsyncEngine, *, count: int = 1, library_id: int | None = None
) -> list[int]:
    global _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    ids: list[int] = []
    async with sm() as session:
        for _ in range(count):
            _seed_counter += 1
            row = UnidentifiedDump(
                path=f"/downloads/unknown-{_seed_counter}.zip",
                size_bytes=1024 + _seed_counter,
                discovered_at=datetime.now(UTC),
                rejection_reason="match:no_game",
                library_id=library_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            ids.append(row.id)
    return ids


@pytest.mark.asyncio
async def test_list_unidentified_paginated(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    await _seed_unidentified(api_engine, count=3)

    response = await api_client.get("/api/v3/rom/unidentified")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    # Every row carries the spec-008 extension columns.
    assert all("rejection_reason" in r for r in rows)


@pytest.mark.asyncio
async def test_list_unidentified_filter_by_library(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    await _seed_unidentified(api_engine, count=2, library_id=1)
    await _seed_unidentified(api_engine, count=3, library_id=2)

    response = await api_client.get(
        "/api/v3/rom/unidentified?library_id=2"
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    assert all(r["library_id"] == 2 for r in rows)


@pytest.mark.asyncio
async def test_delete_unidentified_succeeds(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    [target_id] = await _seed_unidentified(api_engine, count=1)

    response = await api_client.delete(
        f"/api/v3/rom/unidentified/{target_id}"
    )
    assert response.status_code == 204

    # The DB row is gone.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        gone = (
            await session.execute(
                select(UnidentifiedDump).where(
                    UnidentifiedDump.id == target_id
                )
            )
        ).scalar_one_or_none()
        assert gone is None


@pytest.mark.asyncio
async def test_delete_unidentified_404_when_missing(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    response = await api_client.delete("/api/v3/rom/unidentified/9999")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "not_found"


@pytest.mark.asyncio
async def test_delete_unidentified_user_role_forbidden(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    [target_id] = await _seed_unidentified(api_engine, count=1)

    response = await api_client.delete(
        f"/api/v3/rom/unidentified/{target_id}"
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_unidentified_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/rom/unidentified")
    assert response.status_code == 401
