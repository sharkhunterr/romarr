"""Indexer CRUD endpoint tests (T058-T061)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.indexers.models import Indexer
from tests.indexers.api.conftest import seed_admin_and_login

_VALID_PAYLOAD = {
    "name": "Newznab Test",
    "implementation": "newznab",
    "url": "https://nznb.test",
    "api_key": "nznb-key",
    "categories": [1060, 7010],
}


@pytest.mark.asyncio
async def test_create_persists_indexer(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post("/api/v3/indexer", json=_VALID_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Newznab Test"
    assert body["is_configured"] is True
    # api_key NEVER leaks in any response shape.
    assert "api_key" not in body


@pytest.mark.asyncio
async def test_post_with_test_true_runs_connectivity_first(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    torznab_response: Callable[[str], bytes],
) -> None:
    """T058: ?test=true on a happy indexer persists the row; on a
    failing connectivity probe it returns HTTP 400 with no row written."""
    await seed_admin_and_login(api_engine, api_client)

    caps_body = torznab_response("torznab_caps/valid_full.xml")
    with respx.mock:
        def _route(request: httpx.Request) -> httpx.Response:
            t = request.url.params.get("t")
            if t == "caps":
                return httpx.Response(200, content=caps_body)
            if t == "search":
                return httpx.Response(
                    200, content=b"<?xml version='1.0'?><rss><channel/></rss>"
                )
            return httpx.Response(404)

        respx.get("https://nznb.test/api").mock(side_effect=_route)
        response = await api_client.post(
            "/api/v3/indexer?test=true", json=_VALID_PAYLOAD
        )

    assert response.status_code == 201

    # The fail path: 401 on caps → no row written, HTTP 400.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (await session.execute(select(Indexer))).scalars().all()
    assert len(rows) == 1

    with respx.mock:
        respx.get("https://failing.test/api").mock(
            return_value=httpx.Response(401)
        )
        bad_response = await api_client.post(
            "/api/v3/indexer?test=true",
            json={
                **_VALID_PAYLOAD,
                "name": "Failing",
                "url": "https://failing.test",
            },
        )
    assert bad_response.status_code == 400
    assert bad_response.json()["errorCode"] == "auth"

    # Still only one row — the failed test never persisted.
    async with sm() as session:
        rows = (await session.execute(select(Indexer))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_put_re_encrypts_when_api_key_present(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T059: PUT with ``api_key`` re-encrypts; PUT without it leaves
    the existing ciphertext untouched (FR-022)."""
    await seed_admin_and_login(api_engine, api_client)

    create = await api_client.post("/api/v3/indexer", json=_VALID_PAYLOAD)
    indexer_id = create.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        original = (
            await session.execute(
                select(Indexer).where(Indexer.id == indexer_id)
            )
        ).scalar_one()
        original_ciphertext = original.api_key_encrypted

    # PUT without api_key — ciphertext untouched.
    put_no_key = await api_client.put(
        f"/api/v3/indexer/{indexer_id}", json={"name": "Renamed"}
    )
    assert put_no_key.status_code == 200
    async with sm() as session:
        row = (
            await session.execute(
                select(Indexer).where(Indexer.id == indexer_id)
            )
        ).scalar_one()
        assert row.api_key_encrypted == original_ciphertext
        assert row.name == "Renamed"

    # PUT with api_key — ciphertext changes.
    put_with_key = await api_client.put(
        f"/api/v3/indexer/{indexer_id}", json={"api_key": "new-key"}
    )
    assert put_with_key.status_code == 200
    async with sm() as session:
        row = (
            await session.execute(
                select(Indexer).where(Indexer.id == indexer_id)
            )
        ).scalar_one()
        assert row.api_key_encrypted != original_ciphertext


@pytest.mark.asyncio
async def test_post_duplicate_returns_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T060: same (implementation, url) twice → HTTP 409."""
    await seed_admin_and_login(api_engine, api_client)
    first = await api_client.post("/api/v3/indexer", json=_VALID_PAYLOAD)
    assert first.status_code == 201

    second = await api_client.post(
        "/api/v3/indexer", json={**_VALID_PAYLOAD, "name": "Different name"}
    )
    assert second.status_code == 409
    assert second.json()["errorCode"] == "duplicate"


@pytest.mark.asyncio
async def test_delete_removes_indexer(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/indexer", json=_VALID_PAYLOAD)
    indexer_id = create.json()["id"]

    response = await api_client.delete(f"/api/v3/indexer/{indexer_id}")
    assert response.status_code == 204

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(Indexer).where(Indexer.id == indexer_id)
            )
        ).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_test_endpoint_runs_connectivity(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    torznab_response: Callable[[str], bytes],
) -> None:
    """T061: POST /api/v3/indexer/{id}/test runs caps + sample search."""
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/indexer", json=_VALID_PAYLOAD)
    indexer_id = create.json()["id"]

    caps_body = torznab_response("torznab_caps/valid_full.xml")
    with respx.mock:
        def _route(request: httpx.Request) -> httpx.Response:
            t = request.url.params.get("t")
            if t == "caps":
                return httpx.Response(200, content=caps_body)
            if t == "search":
                return httpx.Response(
                    200, content=b"<?xml version='1.0'?><rss><channel/></rss>"
                )
            return httpx.Response(404)

        respx.get("https://nznb.test/api").mock(side_effect=_route)
        response = await api_client.post(
            f"/api/v3/indexer/{indexer_id}/test"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["caps_ok"] is True
    assert body["search_ok"] is True


@pytest.mark.asyncio
async def test_schema_endpoint_returns_known_implementations(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T052: GET /api/v3/indexer/schema returns Newznab + Torznab entries."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.get("/api/v3/indexer/schema")
    assert response.status_code == 200
    rows = response.json()
    impls = {r["implementation"] for r in rows}
    assert impls == {"newznab", "torznab"}


@pytest.mark.asyncio
async def test_list_and_get_round_trip(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/indexer", json=_VALID_PAYLOAD)
    indexer_id = create.json()["id"]

    list_response = await api_client.get("/api/v3/indexer")
    assert list_response.status_code == 200
    assert any(r["id"] == indexer_id for r in list_response.json())

    get_response = await api_client.get(f"/api/v3/indexer/{indexer_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == indexer_id


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/indexer")
    assert response.status_code == 401
