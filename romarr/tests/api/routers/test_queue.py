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
from romarr.domain.models import Game, Platform, Release
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


# ---------------------------------------------------------------------------
# slice 109 — gameId / releaseId filters
# ---------------------------------------------------------------------------


async def _seed_two_games_with_queue(
    engine: AsyncEngine,
) -> tuple[int, int, int]:
    """Two games on the same platform; each gets one Release with
    one queued download. Returns (target_game_id, other_game_id,
    target_release_id) so the test can assert per-game filtering.

    FKs are disabled for the seed (matches the pattern in
    `_seed_queue_entries`) so we don't need a real download_client
    row — the router doesn't read that table."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        await session.execute(text("PRAGMA foreign_keys=OFF"))
        platform = Platform(slug="md-q", name="Mega Drive")
        session.add(platform)
        await session.flush()
        target = Game(
            platform_id=platform.id, slug="target", title="Target"
        )
        other = Game(platform_id=platform.id, slug="other", title="Other")
        session.add_all([target, other])
        await session.flush()
        r_target = Release(game_id=target.id, name="r-target")
        r_other = Release(game_id=other.id, name="r-other")
        session.add_all([r_target, r_other])
        await session.flush()
        # Queue rows: 2 against the target Release, 1 against other.
        now = datetime.now(UTC)
        session.add_all(
            [
                QueueEntry(
                    release_id=r_target.id,
                    download_client_id=1,
                    download_client_native_id="t-1",
                    state="downloading",
                    progress=0.1,
                    last_updated_at=now,
                    attempt_count=0,
                ),
                QueueEntry(
                    release_id=r_target.id,
                    download_client_id=1,
                    download_client_native_id="t-2",
                    state="queued",
                    progress=0.0,
                    last_updated_at=now,
                    attempt_count=0,
                ),
                QueueEntry(
                    release_id=r_other.id,
                    download_client_id=1,
                    download_client_native_id="o-1",
                    state="downloading",
                    progress=0.5,
                    last_updated_at=now,
                    attempt_count=0,
                ),
            ]
        )
        await session.commit()
        return target.id, other.id, r_target.id


@pytest.mark.asyncio
async def test_game_id_filter_keeps_only_target_game_entries(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    target, _, _ = await _seed_two_games_with_queue(api_engine)
    resp = await authed_client.get(
        f"/api/v3/queue?gameId={target}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 2
    native_ids = {r["downloadClientNativeId"] for r in body["records"]}
    assert native_ids == {"t-1", "t-2"}


@pytest.mark.asyncio
async def test_release_id_filter_keeps_only_target_release_entries(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, _, release_id = await _seed_two_games_with_queue(api_engine)
    resp = await authed_client.get(
        f"/api/v3/queue?releaseId={release_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalRecords"] == 2
    assert all(r["releaseId"] == release_id for r in body["records"])


@pytest.mark.asyncio
async def test_game_id_zero_rejected(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get("/api/v3/queue?gameId=0")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# slice 121 — state filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_filter_keeps_only_matching_state(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Three rows seeded across two states (alternating
    downloading / queued via `_seed_queue_entries`).
    `?state=downloading` keeps only the two downloading rows."""
    await _seed_queue_entries(api_engine, count=3)
    resp = await authed_client.get("/api/v3/queue?state=downloading")
    assert resp.status_code == 200
    body = resp.json()
    # The helper alternates: i=0,2 → downloading, i=1 → queued.
    assert body["totalRecords"] == 2
    for record in body["records"]:
        assert record["state"] == "downloading"


@pytest.mark.asyncio
async def test_state_filter_unknown_value_rejected(
    authed_client: httpx.AsyncClient,
) -> None:
    """The Literal-typed param rejects values outside the
    documented state set."""
    resp = await authed_client.get("/api/v3/queue?state=NotAState")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# T045 — DELETE /api/v3/queue/{id} removes the entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_entry_when_remove_from_client_false(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Default ``removeFromClient=false`` only deletes the
    Romarr-side row; no download-client call is made (the
    test fixture has no real client wired)."""
    ids = await _seed_queue_entries(api_engine, count=2)
    target = ids[0]

    resp = await authed_client.delete(f"/api/v3/queue/{target}")
    assert resp.status_code == 204

    # Row gone — list endpoint reports the survivor only.
    listing = await authed_client.get("/api/v3/queue")
    assert listing.status_code == 200
    record_ids = [r["id"] for r in listing.json()["records"]]
    assert target not in record_ids
    assert ids[1] in record_ids


@pytest.mark.asyncio
async def test_delete_returns_404_when_entry_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.delete("/api/v3/queue/99999")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "queue_entry_not_found"


@pytest.mark.asyncio
async def test_delete_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    ids = await _seed_queue_entries(api_engine, count=1)
    resp = await api_client.delete(f"/api/v3/queue/{ids[0]}")
    assert resp.status_code == 401
