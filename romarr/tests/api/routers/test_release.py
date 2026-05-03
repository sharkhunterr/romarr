"""Release write-endpoint tests (slice 98)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.api.models import DEFAULT_TAG_COLOR, Tag, TagAssignment
from romarr.domain.models import Game, Platform, Release
from tests.api.test_auth_endpoints import _seed_admin_user


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


_seed_counter = 0


async def _seed_release(api_engine: AsyncEngine) -> int:
    global _seed_counter
    _seed_counter += 1
    suffix = _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(slug=f"r-pl-{suffix}", name="Mega Drive")
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"r-g-{suffix}",
            title=f"Game {suffix}",
        )
        session.add(game)
        await session.flush()
        release = Release(
            game_id=game.id,
            name=f"Game {suffix} (USA)",
        )
        session.add(release)
        await session.commit()
        return release.id


@pytest.mark.asyncio
async def test_patch_release_toggles_monitored_to_false(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Release default monitored=True. PATCH flips and persists."""
    release_id = await _seed_release(api_engine)

    resp = await authed_client.patch(
        f"/api/v3/rom/release/{release_id}", json={"monitored": False}
    )
    assert resp.status_code == 200
    assert resp.json()["monitored"] is False
    assert resp.json()["id"] == release_id


@pytest.mark.asyncio
async def test_patch_release_toggles_back_to_true(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    release_id = await _seed_release(api_engine)
    await authed_client.patch(
        f"/api/v3/rom/release/{release_id}", json={"monitored": False}
    )
    resp = await authed_client.patch(
        f"/api/v3/rom/release/{release_id}", json={"monitored": True}
    )
    assert resp.status_code == 200
    assert resp.json()["monitored"] is True


@pytest.mark.asyncio
async def test_patch_release_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.patch(
        "/api/v3/rom/release/9999999", json={"monitored": False}
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "release_not_found"


@pytest.mark.asyncio
async def test_patch_release_rejects_unknown_fields(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """`extra=forbid` keeps the surface narrow — Release name /
    region / dump_status edits belong to the import pipeline,
    not to a hand-rolled PATCH."""
    release_id = await _seed_release(api_engine)
    resp = await authed_client.patch(
        f"/api/v3/rom/release/{release_id}",
        json={"monitored": False, "name": "Hacked"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_release_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.patch(
        "/api/v3/rom/release/1", json={"monitored": False}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 152 — POST /api/v3/rom/release/bulk-monitor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_monitor_releases_flips_to_false(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    a = await _seed_release(api_engine)
    b = await _seed_release(api_engine)
    c = await _seed_release(api_engine)

    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-monitor",
        json={"releaseIds": [a, b, c], "monitored": False},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["updated"] == 3
    assert body["missing"] == []


@pytest.mark.asyncio
async def test_bulk_monitor_releases_reports_missing(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    a = await _seed_release(api_engine)
    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-monitor",
        json={"releaseIds": [a, 999_999], "monitored": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 1
    assert body["missing"] == [999_999]


@pytest.mark.asyncio
async def test_bulk_monitor_releases_idempotent(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    a = await _seed_release(api_engine)
    for _ in range(3):
        resp = await authed_client.post(
            "/api/v3/rom/release/bulk-monitor",
            json={"releaseIds": [a], "monitored": True},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1


@pytest.mark.asyncio
async def test_bulk_monitor_releases_rejects_empty_list(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-monitor",
        json={"releaseIds": [], "monitored": False},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_monitor_releases_rejects_too_many(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-monitor",
        json={
            "releaseIds": list(range(1, 502)),
            "monitored": False,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_monitor_releases_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v3/rom/release/bulk-monitor",
        json={"releaseIds": [1], "monitored": False},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 155 — POST /api/v3/rom/release/bulk-delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_delete_releases_drops_rows(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    a = await _seed_release(api_engine)
    b = await _seed_release(api_engine)
    c = await _seed_release(api_engine)

    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-delete",
        json={"releaseIds": [a, b, c]},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["deleted"] == 3
    assert body["missing"] == []

    # The PATCH endpoint surfaces the canonical 404 on each id.
    for rid in (a, b, c):
        row = await authed_client.patch(
            f"/api/v3/rom/release/{rid}", json={"monitored": False}
        )
        assert row.status_code == 404


@pytest.mark.asyncio
async def test_bulk_delete_releases_reports_missing(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    a = await _seed_release(api_engine)
    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-delete",
        json={"releaseIds": [a, 999_999, 888_888]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == 1
    assert body["missing"] == [888_888, 999_999]


@pytest.mark.asyncio
async def test_bulk_delete_releases_idempotent(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    a = await _seed_release(api_engine)
    first = await authed_client.post(
        "/api/v3/rom/release/bulk-delete", json={"releaseIds": [a]}
    )
    assert first.status_code == 200
    assert first.json()["deleted"] == 1

    second = await authed_client.post(
        "/api/v3/rom/release/bulk-delete", json={"releaseIds": [a]}
    )
    assert second.status_code == 200
    assert second.json()["deleted"] == 0
    assert second.json()["missing"] == [a]


@pytest.mark.asyncio
async def test_bulk_delete_releases_rejects_empty_list(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-delete", json={"releaseIds": []}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_releases_rejects_too_many(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-delete",
        json={"releaseIds": list(range(1, 502))},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_releases_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v3/rom/release/bulk-delete",
        json={"releaseIds": [1]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 165 — bulk-delete releases sweeps tag_assignment rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_delete_releases_sweeps_tag_assignment(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Deleting a Release must drop its rows from the polymorphic
    ``tag_assignment`` table."""
    a = await _seed_release(api_engine)
    b = await _seed_release(api_engine)

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        # Seed Tag + TagAssignment rows (no bulk-tag surface ships
        # for releases yet — slice 154 only covers games).
        session.add(
            Tag(
                id=1,
                name="release-tag-1",
                label="Release Tag 1",
                color=DEFAULT_TAG_COLOR,
            )
        )
        await session.flush()
        session.add(
            TagAssignment(tag_id=1, entity_type="release", entity_id=a)
        )
        session.add(
            TagAssignment(tag_id=1, entity_type="release", entity_id=b)
        )
        await session.commit()

    resp = await authed_client.post(
        "/api/v3/rom/release/bulk-delete",
        json={"releaseIds": [a]},
    )
    assert resp.status_code == 200

    async with sm() as session:
        rows = (
            await session.execute(
                TagAssignment.__table__.select().where(
                    TagAssignment.entity_type == "release",
                )
            )
        ).all()
    pairs = {(row.tag_id, row.entity_id) for row in rows}
    # Only B's assignment survives.
    assert pairs == {(1, b)}
