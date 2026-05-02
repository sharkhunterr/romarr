"""Queue router tests (T044, FR-014).

This slice ships the GET (list) endpoint only. DELETE and POST
``/{id}/retry`` need the spec 005 download-client integration
and land in a follow-up slice.

QueueEntry has FKs to ``release.id`` and ``download_client.id``.
The list endpoint doesn't traverse those — the router projects
flat columns. To keep the seeding shallow we drop FKs for the
test session via ``PRAGMA foreign_keys=OFF`` (production keeps
them ON; the FKs are enforced by the spec 005 reconciler insert
path which is outside the router's scope)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.api.models import QueueEntry
from tests.api.test_auth_endpoints import _seed_admin_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_queue_entries(
    engine: AsyncEngine, *, count: int = 3
) -> list[int]:
    """Insert ``count`` queue rows with monotonically increasing
    ``last_updated_at`` so sort tests have a stable ordering."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    ids: list[int] = []
    async with sm() as session:
        await session.execute(text("PRAGMA foreign_keys=OFF"))
        now = datetime.now(UTC)
        for i in range(count):
            row = QueueEntry(
                release_id=100 + i,
                download_client_id=1,
                download_client_native_id=f"hash-{i}",
                state="downloading" if i % 2 == 0 else "queued",
                progress=0.1 * (i + 1),
                size_bytes=1024 * (i + 1),
                eta_seconds=60 * (i + 1),
                last_updated_at=now.replace(microsecond=i * 1000),
                attempt_count=0,
            )
            session.add(row)
            await session.flush()
            ids.append(row.id)
        await session.commit()
    return ids


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
# T044 — GET /api/v3/queue lists in-flight rows with progress / state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lists_in_flight_with_canonical_envelope(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """The list endpoint returns the canonical pagination
    envelope. Each record carries the documented camelCase keys
    (releaseId / downloadClientId / state / progress / etaSeconds
    / sizeBytes)."""
    await _seed_queue_entries(api_engine, count=3)

    resp = await authed_client.get("/api/v3/queue")
    assert resp.status_code == 200
    body = resp.json()

    # Canonical pagination envelope shape (FR-007).
    assert body["page"] == 1
    assert body["pageSize"] == 50
    assert body["sortDirection"] == "asc"
    assert body["totalRecords"] == 3
    assert len(body["records"]) == 3

    # Sonarr-shape record fields.
    record = body["records"][0]
    expected_keys = {
        "id",
        "releaseId",
        "downloadClientId",
        "downloadClientNativeId",
        "state",
        "progress",
        "sizeBytes",
        "etaSeconds",
        "lastUpdatedAt",
        "errorMsg",
        "attemptCount",
        "lastAttemptAt",
        "createdAt",
    }
    assert expected_keys.issubset(record.keys())


# ---------------------------------------------------------------------------
# Pagination & sort
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_page_size_caps_records_returned(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """``?pageSize=2`` returns at most two rows; total still
    reports the full count."""
    await _seed_queue_entries(api_engine, count=5)

    resp = await authed_client.get("/api/v3/queue?pageSize=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 5
    assert body["pageSize"] == 2
    assert len(body["records"]) == 2


@pytest.mark.asyncio
async def test_sort_by_state_descending(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """The ``state`` column is in the sortable whitelist;
    descending order returns ``queued`` before ``downloading``
    alphabetically."""
    await _seed_queue_entries(api_engine, count=3)

    resp = await authed_client.get(
        "/api/v3/queue?sortKey=state&sortDirection=desc"
    )
    assert resp.status_code == 200
    body = resp.json()
    states = [record["state"] for record in body["records"]]
    assert states == sorted(states, reverse=True)


@pytest.mark.asyncio
async def test_invalid_sort_key_returns_400(
    authed_client: httpx.AsyncClient,
) -> None:
    """``?sortKey=NotARealField`` trips the canonical
    pagination guard (FR-008)."""
    resp = await authed_client.get(
        "/api/v3/queue?sortKey=NotARealField"
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "invalid_sort_key"


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/queue")
    assert resp.status_code == 401
    assert resp.json()["errorCode"] == "unauthenticated"


@pytest.mark.asyncio
async def test_empty_queue_returns_zero_records(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get("/api/v3/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 0
    assert body["records"] == []
