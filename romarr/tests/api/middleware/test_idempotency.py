"""Idempotency-Key middleware tests (T028, T029, T030, FR-020 /
FR-021 / FR-025).

The tests exercise the middleware end-to-end via the live
``api_client`` fixture against the POST /api/v3/tag endpoint —
that endpoint is admin-write, returns a body, and surfaces a
deterministic 409 on duplicate `name`. If the middleware works,
replaying the same key + body will *not* hit the duplicate-name
guard (since the second call is short-circuited from the cache).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.api.models import IdempotencyCache
from tests.api.test_auth_endpoints import _seed_admin_user

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def authed_client(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> httpx.AsyncClient:
    await _seed_admin_user(api_engine)
    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert login.status_code == 204
    return api_client


# ---------------------------------------------------------------------------
# T028 — replay returns the cached response (no duplicate work)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_returns_cached_response(
    authed_client: httpx.AsyncClient,
) -> None:
    """Two POSTs with the same Idempotency-Key + identical body
    return the same status + body. Without the middleware, the
    second call would hit the unique-name guard and return 409 —
    the cache short-circuits before the handler runs."""
    payload = {"name": "idempotent", "label": "Idempotent"}
    headers = {"Idempotency-Key": "key-123"}

    first = await authed_client.post(
        "/api/v3/tag", json=payload, headers=headers
    )
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["name"] == "idempotent"

    second = await authed_client.post(
        "/api/v3/tag", json=payload, headers=headers
    )
    assert second.status_code == 201
    assert second.json() == first_body
    # The middleware tags replays so callers can detect them.
    assert second.headers.get("x-idempotent-replay") == "true"


@pytest.mark.asyncio
async def test_no_idempotency_key_passes_through(
    authed_client: httpx.AsyncClient,
) -> None:
    """Without an Idempotency-Key header, the middleware is a
    no-op. The second POST hits the duplicate-name guard at the
    handler level and returns 409, proving the cache wasn't
    consulted."""
    payload = {"name": "no-key", "label": "No Key"}

    first = await authed_client.post("/api/v3/tag", json=payload)
    assert first.status_code == 201

    second = await authed_client.post("/api/v3/tag", json=payload)
    assert second.status_code == 409
    assert second.json()["errorCode"] == "tag_name_conflict"


# ---------------------------------------------------------------------------
# T029 — body mismatch returns 422 with the documented errorCode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_mismatch_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    """Replaying the same key with a *different* body MUST surface
    HTTP 422 with errorCode ``idempotency_key_body_mismatch``
    (FR-021). The original cached response is not served."""
    headers = {"Idempotency-Key": "key-mismatch"}

    first = await authed_client.post(
        "/api/v3/tag",
        json={"name": "first", "label": "First"},
        headers=headers,
    )
    assert first.status_code == 201

    second = await authed_client.post(
        "/api/v3/tag",
        json={"name": "first", "label": "Different label"},  # body changed
        headers=headers,
    )
    assert second.status_code == 422
    body = second.json()
    assert body["errorCode"] == "idempotency_key_body_mismatch"


# ---------------------------------------------------------------------------
# T030 — 24h TTL: expired rows are treated as fresh requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_cache_row_is_treated_as_miss(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Spec data-model: rows expire ``created_at + 24 hours``.
    A replay after expiry must re-run the handler. We simulate
    aging by writing the row's ``expires_at`` to the past
    directly — equivalent to freezegun-advancing 25 h, but
    deterministic and faster."""
    payload = {"name": "expires-soon", "label": "Expires"}
    headers = {"Idempotency-Key": "key-ttl"}

    first = await authed_client.post(
        "/api/v3/tag", json=payload, headers=headers
    )
    assert first.status_code == 201

    # Age the cache row past its TTL.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    async with sm() as session:
        await session.execute(
            update(IdempotencyCache)
            .where(IdempotencyCache.key == "key-ttl")
            .values(expires_at=one_hour_ago)
        )
        await session.commit()

    # Replay — the cache row is expired, so the middleware runs
    # the handler. The handler hits the duplicate-name guard and
    # returns 409. (Proves the cache wasn't served.)
    second = await authed_client.post(
        "/api/v3/tag", json=payload, headers=headers
    )
    assert second.status_code == 409
    assert second.json()["errorCode"] == "tag_name_conflict"


# ---------------------------------------------------------------------------
# Sanity: GET requests bypass the middleware entirely.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_request_with_idempotency_key_bypasses(
    authed_client: httpx.AsyncClient,
) -> None:
    """Safe methods (GET / HEAD / OPTIONS) bypass the middleware.
    The Idempotency-Key header on a GET is ignored — both calls
    return fresh responses, no replay header set."""
    first = await authed_client.get(
        "/api/v3/tag",
        headers={"Idempotency-Key": "irrelevant"},
    )
    assert first.status_code == 200
    assert "x-idempotent-replay" not in {
        k.lower() for k in first.headers
    }


@pytest.mark.asyncio
async def test_canonical_json_normalisation(
    authed_client: httpx.AsyncClient,
) -> None:
    """JCS-style canonicalisation: re-ordering keys / re-spacing
    JSON does NOT count as a body mismatch. The replay's hash
    matches the original."""
    headers = {"Idempotency-Key": "key-canonical"}

    first = await authed_client.post(
        "/api/v3/tag",
        json={"name": "canon", "label": "Canon"},
        headers=headers,
    )
    assert first.status_code == 201

    # Same logical body, different serialised form — Python's json
    # may insert different whitespace / key order on the wire.
    # Send raw bytes with deliberate re-ordering.
    second = await authed_client.post(
        "/api/v3/tag",
        content=b'{ "label" : "Canon" , "name" : "canon" }',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert second.status_code == 201
    assert second.headers.get("x-idempotent-replay") == "true"
