"""Tag CRUD endpoint tests (T050, T051, T052).

Covers the four CRUD verbs plus the polymorphic-detail endpoint.
The router admin-gates all writes via :func:`require_admin`; the
read endpoints accept any authenticated principal via
:func:`require_readonly`.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.api.models import DEFAULT_TAG_COLOR, Tag, TagAssignment
from tests.api.test_auth_endpoints import _seed_admin_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def authed_client(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> httpx.AsyncClient:
    """Return a client logged in as an admin via cookie session."""
    await _seed_admin_user(api_engine)
    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert login.status_code == 204
    return api_client


# ---------------------------------------------------------------------------
# T050 — full CRUD round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_get_put_delete_round_trip(
    authed_client: httpx.AsyncClient,
) -> None:
    # --- POST creates the row with the documented defaults ---
    create = await authed_client.post(
        "/api/v3/tag",
        json={"name": "family-friendly", "label": "Family Friendly"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "family-friendly"
    assert body["label"] == "Family Friendly"
    assert body["color"] == DEFAULT_TAG_COLOR  # spec 014 brand
    tag_id = body["id"]

    # --- GET list returns the new tag ---
    listing = await authed_client.get("/api/v3/tag")
    assert listing.status_code == 200
    assert any(t["id"] == tag_id for t in listing.json())

    # --- GET single returns the documented shape ---
    read = await authed_client.get(f"/api/v3/tag/{tag_id}")
    assert read.status_code == 200
    assert read.json()["name"] == "family-friendly"

    # --- PUT updates label + colour ---
    updated = await authed_client.put(
        f"/api/v3/tag/{tag_id}",
        json={"label": "Family", "color": "#FF8800"},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "Family"
    assert updated.json()["color"] == "#FF8800"

    # --- DELETE removes the row ---
    removed = await authed_client.delete(f"/api/v3/tag/{tag_id}")
    assert removed.status_code == 204

    not_found = await authed_client.get(f"/api/v3/tag/{tag_id}")
    assert not_found.status_code == 404


# ---------------------------------------------------------------------------
# T051 — DELETE in-use returns 409 unless ?force=true
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_in_use_returns_409(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    create = await authed_client.post(
        "/api/v3/tag", json={"name": "in-use", "label": "In Use"}
    )
    tag_id = create.json()["id"]

    # Manually pin an assignment row so the tag looks in-use.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            TagAssignment(
                tag_id=tag_id, entity_type="game", entity_id=42
            )
        )
        await session.commit()

    blocked = await authed_client.delete(f"/api/v3/tag/{tag_id}")
    assert blocked.status_code == 409
    body = blocked.json()
    assert body["errorCode"] == "tag_in_use"


@pytest.mark.asyncio
async def test_delete_in_use_with_force_cascades(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    create = await authed_client.post(
        "/api/v3/tag", json={"name": "force-me", "label": "Force"}
    )
    tag_id = create.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            TagAssignment(
                tag_id=tag_id, entity_type="release", entity_id=7
            )
        )
        await session.commit()

    forced = await authed_client.delete(
        f"/api/v3/tag/{tag_id}?force=true"
    )
    assert forced.status_code == 204

    # The cascade ran — both the tag and the assignment row are gone.
    async with sm() as session:
        tag = (
            await session.execute(select(Tag).where(Tag.id == tag_id))
        ).scalar_one_or_none()
        assignment = (
            await session.execute(
                select(TagAssignment).where(
                    TagAssignment.tag_id == tag_id
                )
            )
        ).scalar_one_or_none()
    assert tag is None
    assert assignment is None


# ---------------------------------------------------------------------------
# T052 — /tag/detail/{id} lists every entity using the tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_lists_resources_grouped_by_entity_type(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    create = await authed_client.post(
        "/api/v3/tag",
        json={"name": "detail-me", "label": "Detail"},
    )
    tag_id = create.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add_all(
            [
                TagAssignment(
                    tag_id=tag_id, entity_type="game", entity_id=10
                ),
                TagAssignment(
                    tag_id=tag_id, entity_type="game", entity_id=20
                ),
                TagAssignment(
                    tag_id=tag_id,
                    entity_type="indexer",
                    entity_id=5,
                ),
                TagAssignment(
                    tag_id=tag_id,
                    entity_type="notification",
                    entity_id=99,
                ),
            ]
        )
        await session.commit()

    detail = await authed_client.get(f"/api/v3/tag/detail/{tag_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == tag_id
    assert body["label"] == "Detail"
    assert body["gameIds"] == [10, 20]
    assert body["indexerIds"] == [5]
    assert body["notificationIds"] == [99]
    assert body["releaseIds"] == []


# ---------------------------------------------------------------------------
# Validation + auth gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_without_auth_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    """Mutations require auth; the global handler returns the
    canonical envelope on 401."""
    resp = await api_client.post(
        "/api/v3/tag", json={"name": "x", "label": "X"}
    )
    assert resp.status_code == 401
    assert resp.json()["errorCode"] == "unauthenticated"


@pytest.mark.asyncio
async def test_create_with_duplicate_name_returns_409(
    authed_client: httpx.AsyncClient,
) -> None:
    """The unique constraint on ``tag.name`` surfaces as a 409
    with errorCode ``tag_name_conflict``."""
    await authed_client.post(
        "/api/v3/tag", json={"name": "dup", "label": "First"}
    )
    second = await authed_client.post(
        "/api/v3/tag", json={"name": "dup", "label": "Second"}
    )
    assert second.status_code == 409
    assert second.json()["errorCode"] == "tag_name_conflict"


@pytest.mark.asyncio
async def test_create_with_invalid_color_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    """Pydantic regex catches malformed colour strings before the
    DB sees them."""
    resp = await authed_client.post(
        "/api/v3/tag",
        json={"name": "bad-color", "label": "Bad", "color": "purple"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_with_invalid_name_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    """Spaces and uppercase are rejected by the slug pattern."""
    resp = await authed_client.post(
        "/api/v3/tag",
        json={"name": "Has Space", "label": "X"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# slice 135 — usage_count on the list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tags_carries_usage_count(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Two tags: one with three assignments across multiple
    entity types, one with zero. The list response surfaces the
    aggregate counts."""
    used_resp = await authed_client.post(
        "/api/v3/tag", json={"name": "used", "label": "Used"}
    )
    unused_resp = await authed_client.post(
        "/api/v3/tag", json={"name": "unused", "label": "Unused"}
    )
    used_id = used_resp.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add_all(
            [
                TagAssignment(
                    tag_id=used_id, entity_type="game", entity_id=1
                ),
                TagAssignment(
                    tag_id=used_id, entity_type="game", entity_id=2
                ),
                TagAssignment(
                    tag_id=used_id,
                    entity_type="indexer",
                    entity_id=7,
                ),
            ]
        )
        await session.commit()

    resp = await authed_client.get("/api/v3/tag")
    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.json()}
    assert by_id[used_id]["usageCount"] == 3
    assert by_id[unused_resp.json()["id"]]["usageCount"] == 0
