"""Quality profile CRUD endpoints (T056 + auth gating + FR-032a)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.profiles.models import QualityProfile
from tests.profiles.api.conftest import seed_user_and_login

_VALID_PAYLOAD = {
    "name": "Custom Q",
    "allowed_formats": ["raw", "zip"],
    "preferred_format": "zip",
    "require_dat_verified": False,
    "allow_archive_double_compression": False,
    "upgrade_until_format": "zip",
}


@pytest.mark.asyncio
async def test_full_crud_round_trip(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")

    create = await api_client.post(
        "/api/v3/qualityprofile", json=_VALID_PAYLOAD
    )
    assert create.status_code == 201
    row = create.json()
    assert row["name"] == "Custom Q"

    listing = await api_client.get("/api/v3/qualityprofile")
    assert listing.status_code == 200
    assert any(r["id"] == row["id"] for r in listing.json())

    fetch = await api_client.get(f"/api/v3/qualityprofile/{row['id']}")
    assert fetch.status_code == 200

    update = await api_client.put(
        f"/api/v3/qualityprofile/{row['id']}", json={"name": "Renamed"}
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Renamed"

    delete = await api_client.delete(f"/api/v3/qualityprofile/{row['id']}")
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_post_duplicate_returns_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    first = await api_client.post(
        "/api/v3/qualityprofile", json=_VALID_PAYLOAD
    )
    assert first.status_code == 201

    second = await api_client.post(
        "/api/v3/qualityprofile", json=_VALID_PAYLOAD
    )
    assert second.status_code == 409
    assert second.json()["errorCode"] == "duplicate"


@pytest.mark.asyncio
async def test_post_with_validation_error_returns_422(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    bad = {**_VALID_PAYLOAD, "preferred_format": "not-in-allowed"}
    response = await api_client.post("/api/v3/qualityprofile", json=bad)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_put_flips_is_user_modified(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """FR-003a: any UPDATE through the API stamps is_user_modified=true."""
    await seed_user_and_login(api_engine, api_client, role="admin")
    create = await api_client.post(
        "/api/v3/qualityprofile", json=_VALID_PAYLOAD
    )
    row_id = create.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        before = (
            await session.execute(
                select(QualityProfile).where(QualityProfile.id == row_id)
            )
        ).scalar_one()
        assert before.is_user_modified is False

    await api_client.put(
        f"/api/v3/qualityprofile/{row_id}", json={"name": "Edited"}
    )

    async with sm() as session:
        after = (
            await session.execute(
                select(QualityProfile).where(QualityProfile.id == row_id)
            )
        ).scalar_one()
        assert after.is_user_modified is True


# ---------------------------------------------------------------------------
# FR-032a — admin-only mutations, reads accessible to any authenticated user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/qualityprofile")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_role_can_read(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A non-admin user can list profiles (read access for any authenticated user)."""
    await seed_user_and_login(api_engine, api_client, role="user")
    listing = await api_client.get("/api/v3/qualityprofile")
    assert listing.status_code == 200


@pytest.mark.asyncio
async def test_user_role_blocked_from_create(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    response = await api_client.post(
        "/api/v3/qualityprofile", json=_VALID_PAYLOAD
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_role_blocked_from_delete(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Seed a profile via direct DB insert, then have a user try to delete via API."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = QualityProfile(
            name="x",
            allowed_formats=["raw"],
            preferred_format="raw",
            upgrade_until_format="raw",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        row_id = row.id

    await seed_user_and_login(api_engine, api_client, role="user")
    response = await api_client.delete(f"/api/v3/qualityprofile/{row_id}")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# T062 — JSON Schema endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_endpoint_returns_json_schema(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    response = await api_client.get("/api/v3/qualityprofile/schema")
    assert response.status_code == 200
    schema = response.json()
    # JSON Schema documents declare a `properties` map and a `type`.
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert "allowed_formats" in schema["properties"]
