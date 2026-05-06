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


# ---------------------------------------------------------------------------
# Slice 344: input sanitisation — paste guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_strips_trailing_api_from_url(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A pasted Prowlarr feed URL ending in ``/api`` is normalised so
    the client's own ``/api`` suffix doesn't double up and bounce
    through Prowlarr's login redirect."""
    await seed_admin_and_login(api_engine, api_client)
    payload = {
        **_VALID_PAYLOAD,
        "url": "https://nznb.test/5/api/",
    }
    response = await api_client.post("/api/v3/indexer", json=payload)
    assert response.status_code == 201
    assert response.json()["url"] == "https://nznb.test/5"


@pytest.mark.asyncio
async def test_create_round_trips_api_key_without_quotes(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Decrypting the persisted blob yields the raw key — no JSON
    quoting layer that would be sent verbatim to the upstream and
    produce a silent 401."""
    from romarr.metadata.encryption import decrypt_secret

    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/indexer",
        json={**_VALID_PAYLOAD, "api_key": "plain-secret-key"},
    )
    assert response.status_code == 201
    indexer_id = response.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(Indexer).where(Indexer.id == indexer_id)
            )
        ).scalar_one()
        assert row.api_key_encrypted is not None
        assert decrypt_secret(row.api_key_encrypted) == "plain-secret-key"


@pytest.mark.asyncio
async def test_create_strips_quotes_around_api_key(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Operators sometimes copy a key with the surrounding double or
    single quotes from a logs/UI snippet; the create handler trims
    one balanced layer before encryption."""
    from romarr.metadata.encryption import decrypt_secret

    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/indexer",
        json={**_VALID_PAYLOAD, "api_key": '"abcdef0123456789"'},
    )
    assert response.status_code == 201
    indexer_id = response.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(Indexer).where(Indexer.id == indexer_id)
            )
        ).scalar_one()
        assert decrypt_secret(row.api_key_encrypted) == "abcdef0123456789"


@pytest.mark.asyncio
async def test_put_normalises_url_and_strips_api_key_quotes(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    from romarr.metadata.encryption import decrypt_secret

    await seed_admin_and_login(api_engine, api_client)
    create = await api_client.post("/api/v3/indexer", json=_VALID_PAYLOAD)
    indexer_id = create.json()["id"]

    response = await api_client.put(
        f"/api/v3/indexer/{indexer_id}",
        json={
            "url": "https://nznb.test/5/api",
            "api_key": "  '  rotated-key  '  ",
        },
    )
    assert response.status_code == 200
    assert response.json()["url"] == "https://nznb.test/5"

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(Indexer).where(Indexer.id == indexer_id)
            )
        ).scalar_one()
        assert decrypt_secret(row.api_key_encrypted) == "rotated-key"


def test_decrypt_secret_strips_legacy_json_quotes() -> None:
    """Blobs persisted before the encrypt-side fix were wrapped via
    ``json.dumps`` and decode to ``'"…"'``. ``decrypt_secret`` peels
    off one balanced layer so existing rows decode cleanly without
    a data migration."""
    import json as _json

    from romarr.metadata.encryption import decrypt_secret, encrypt

    legacy_blob = encrypt(_json.dumps("hex-key-32").encode("utf-8"))
    assert decrypt_secret(legacy_blob) == "hex-key-32"

    new_blob = encrypt(b"hex-key-32")
    assert decrypt_secret(new_blob) == "hex-key-32"
