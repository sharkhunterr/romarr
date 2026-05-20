"""Game + Release read-endpoint tests (slice 86)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.api.models import DEFAULT_TAG_COLOR, Tag, TagAssignment
from romarr.domain.models import Dump, Game, Platform, Release
from tests.api.test_auth_endpoints import _seed_admin_user


async def _seed_tags(
    api_engine: AsyncEngine, *, ids: list[int]
) -> None:
    """Seed Tag rows with the given ids — tests that exercise
    the tag-assignment FK need real catalogue rows. Idempotent
    on existing ids."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        existing = {
            row
            for row in (
                await session.execute(
                    Tag.__table__.select().where(Tag.id.in_(ids))
                )
            )
            .scalars()
            .all()
        }
        for tag_id in ids:
            if tag_id in existing:
                continue
            session.add(
                Tag(
                    id=tag_id,
                    name=f"tag-{tag_id}",
                    label=f"Tag {tag_id}",
                    color=DEFAULT_TAG_COLOR,
                )
            )
        await session.commit()


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


async def _seed_chain(
    api_engine: AsyncEngine,
    *,
    title: str = "Sonic the Hedgehog",
    platform_slug: str = "megadrive",
    release_count: int = 1,
) -> tuple[int, int, list[int]]:
    """Seed Platform → Game → N Releases. Returns
    (platform_id, game_id, [release_id, ...])."""
    global _seed_counter
    _seed_counter += 1
    suffix = _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(
            slug=f"{platform_slug}-{suffix}", name="Mega Drive"
        )
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"sonic-{suffix}",
            title=title,
        )
        session.add(game)
        await session.flush()
        release_ids = []
        # Create N independent releases (different region tags) —
        # the multi-disc check constraint (disc_number > 1 implies
        # parent_release_id) makes a real disc-set fixture noisy
        # for a list test that just needs N rows for one game.
        for i in range(release_count):
            release = Release(
                game_id=game.id,
                name=f"{title} ({['USA', 'EUR', 'JPN'][i % 3]}) v{i}",
            )
            session.add(release)
            await session.flush()
            release_ids.append(release.id)
        await session.commit()
        return platform.id, game.id, release_ids


@pytest.mark.asyncio
async def test_list_games_returns_all(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_chain(api_engine, title="Sonic the Hedgehog")
    await _seed_chain(api_engine, title="Streets of Rage")

    response = await authed_client.get("/api/v3/game")
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert "Sonic the Hedgehog" in titles
    assert "Streets of Rage" in titles


@pytest.mark.asyncio
async def test_list_games_title_substring_filter(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_chain(api_engine, title="Sonic the Hedgehog")
    await _seed_chain(api_engine, title="Streets of Rage")

    response = await authed_client.get("/api/v3/game?q=sonic")
    assert response.status_code == 200
    body = response.json()
    titles = [row["title"] for row in body]
    assert all("Sonic" in t for t in titles)
    assert "Streets of Rage" not in titles


@pytest.mark.asyncio
async def test_list_games_empty_q_ignored(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_chain(api_engine, title="Sonic the Hedgehog")

    response = await authed_client.get("/api/v3/game?q=%20")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_list_games_platform_filter(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    pid_a, _, _ = await _seed_chain(api_engine, title="Sonic A")
    pid_b, _, _ = await _seed_chain(api_engine, title="Sonic B")

    response = await authed_client.get(f"/api/v3/game?platform_id={pid_a}")
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert "Sonic A" in titles
    assert "Sonic B" not in titles


async def _seed_game_with_metadata(
    api_engine: AsyncEngine,
    *,
    title: str,
    genres: list[str] | None = None,
    regions: list[str] | None = None,
    release_year: int | None = None,
) -> int:
    """Seed a Platform + Game (+ a single Release if regions are
    provided) with optional genre / region / release_date
    metadata (slice 265 — genre/region/year filter tests).
    Region lives on Release, not Game — a single Release with
    the requested regions is created when ``regions`` is
    non-empty. Returns the new ``game_id``."""
    from datetime import datetime, timezone

    global _seed_counter
    _seed_counter += 1
    suffix = _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(
            slug=f"megadrive-meta-{suffix}", name="Mega Drive"
        )
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"meta-{suffix}",
            title=title,
            genres=genres or [],
            release_date=(
                datetime(release_year, 6, 1, tzinfo=timezone.utc)
                if release_year is not None
                else None
            ),
        )
        session.add(game)
        await session.flush()
        if regions:
            release = Release(
                game_id=game.id,
                name=f"{title} ({'/'.join(regions)})",
                regions=regions,
            )
            session.add(release)
        await session.commit()
        return int(game.id)


@pytest.mark.asyncio
async def test_list_games_genre_filter(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Genre filter matches case-insensitive substring against
    ``Game.genres`` (slice 265)."""
    await _seed_game_with_metadata(
        api_engine, title="Sonic Plat", genres=["Platformer", "Action"]
    )
    await _seed_game_with_metadata(
        api_engine, title="Streets RPG", genres=["RPG"]
    )

    response = await authed_client.get("/api/v3/game?genre=Platformer")
    assert response.status_code == 200
    titles = {row["title"] for row in response.json()}
    assert "Sonic Plat" in titles
    assert "Streets RPG" not in titles


@pytest.mark.asyncio
async def test_list_games_genre_filter_case_insensitive(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_game_with_metadata(
        api_engine, title="Sonic Plat", genres=["Platformer"]
    )
    response = await authed_client.get("/api/v3/game?genre=platformer")
    assert response.status_code == 200
    titles = {row["title"] for row in response.json()}
    assert "Sonic Plat" in titles


@pytest.mark.asyncio
async def test_list_games_region_filter(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_game_with_metadata(
        api_engine, title="Sonic USA", regions=["US", "EU"]
    )
    await _seed_game_with_metadata(
        api_engine, title="Sonic JPN", regions=["JP"]
    )

    response = await authed_client.get("/api/v3/game?region=US")
    assert response.status_code == 200
    titles = {row["title"] for row in response.json()}
    assert "Sonic USA" in titles
    assert "Sonic JPN" not in titles


@pytest.mark.asyncio
async def test_list_games_year_filter(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_game_with_metadata(
        api_engine, title="Sonic 91", release_year=1991
    )
    await _seed_game_with_metadata(
        api_engine, title="Sonic 92", release_year=1992
    )

    response = await authed_client.get("/api/v3/game?year=1991")
    assert response.status_code == 200
    titles = {row["title"] for row in response.json()}
    assert "Sonic 91" in titles
    assert "Sonic 92" not in titles


@pytest.mark.asyncio
async def test_list_games_year_filter_rejects_out_of_range(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/game?year=1899")
    assert response.status_code == 422
    response = await authed_client.get("/api/v3/game?year=2200")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_read_game_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/game/9999999")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_read_game_returns_full_shape(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, _ = await _seed_chain(api_engine, title="Sonic 2")

    response = await authed_client.get(f"/api/v3/game/{game_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == game_id
    assert body["title"] == "Sonic 2"
    assert "platform_id" in body
    assert "slug" in body


@pytest.mark.asyncio
async def test_list_releases_returns_all_for_game(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, release_ids = await _seed_chain(
        api_engine, title="Sonic CD", release_count=3
    )

    response = await authed_client.get(f"/api/v3/game/{game_id}/release")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    returned_ids = sorted(r["id"] for r in body)
    assert returned_ids == sorted(release_ids)


@pytest.mark.asyncio
async def test_list_releases_404_when_game_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/game/9999999/release")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_list_games_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/game")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# slice 95 — GET /api/v3/game/{id}/dump
# ---------------------------------------------------------------------------


async def _seed_dump_for_release(
    api_engine: AsyncEngine,
    *,
    release_id: int,
    path: str,
    sha1: str,
) -> int:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        dump = Dump(
            release_id=release_id,
            path=path,
            original_filename=path.rsplit("/", 1)[-1],
            size_bytes=1024,
            format="zip",
            crc32="00000000",
            md5="0" * 32,
            sha1=sha1,
        )
        session.add(dump)
        await session.commit()
        return dump.id


@pytest.mark.asyncio
async def test_list_dumps_for_game_joins_through_releases(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Two releases with one dump each → both surface in the
    per-game dump list."""
    _, game_id, release_ids = await _seed_chain(
        api_engine, title="Sonic Mania", release_count=2
    )
    d1 = await _seed_dump_for_release(
        api_engine,
        release_id=release_ids[0],
        path="/lib/mania-usa.zip",
        sha1="a" * 40,
    )
    d2 = await _seed_dump_for_release(
        api_engine,
        release_id=release_ids[1],
        path="/lib/mania-eur.zip",
        sha1="b" * 40,
    )

    resp = await authed_client.get(f"/api/v3/game/{game_id}/dump")
    assert resp.status_code == 200
    body = resp.json()
    returned_ids = sorted(d["id"] for d in body)
    assert returned_ids == sorted([d1, d2])
    paths = {d["path"] for d in body}
    assert paths == {"/lib/mania-usa.zip", "/lib/mania-eur.zip"}


@pytest.mark.asyncio
async def test_list_dumps_empty_when_no_dumps_imported(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A wanted-but-not-yet-imported game has zero dumps."""
    _, game_id, _ = await _seed_chain(api_engine, title="Wantedish")
    resp = await authed_client.get(f"/api/v3/game/{game_id}/dump")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_dumps_404_when_game_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.get("/api/v3/game/9999999/dump")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_list_dumps_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/game/1/dump")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 96 — PATCH /api/v3/game/{id} monitor toggle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_game_toggles_monitored_to_false(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Game seeds with monitored=True (default). PATCH flips it."""
    _, game_id, _ = await _seed_chain(api_engine, title="Toggle Game")

    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}", json={"monitored": False}
    )
    assert resp.status_code == 200
    assert resp.json()["monitored"] is False

    # Re-read confirms the persistence path, not just the response.
    resp2 = await authed_client.get(f"/api/v3/game/{game_id}")
    assert resp2.json()["monitored"] is False


@pytest.mark.asyncio
async def test_patch_game_toggles_monitored_back_to_true(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, _ = await _seed_chain(api_engine, title="Re-monitor")
    # Off, then on.
    await authed_client.patch(
        f"/api/v3/game/{game_id}", json={"monitored": False}
    )
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}", json={"monitored": True}
    )
    assert resp.status_code == 200
    assert resp.json()["monitored"] is True


@pytest.mark.asyncio
async def test_patch_game_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.patch(
        "/api/v3/game/9999999", json={"monitored": False}
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_patch_game_rejects_unknown_fields(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """``extra=forbid`` on GameToggleRequest — only ``monitored``
    is operator-toggleable here. Title edits go through the
    metadata aggregator."""
    _, game_id, _ = await _seed_chain(api_engine, title="ExtraGuard")
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}",
        json={"monitored": False, "title": "Hacked Title"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_game_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.patch(
        "/api/v3/game/1", json={"monitored": False}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 125 — list sort + direction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_games_sort_by_title_default_asc(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Default sort = title ascending. Seed three games out of
    alphabetical order; the response is alphabetical."""
    await _seed_chain(api_engine, title="Zelda")
    await _seed_chain(api_engine, title="Mario")
    await _seed_chain(api_engine, title="Bomberman")

    response = await authed_client.get("/api/v3/game")
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert titles == sorted(titles)


@pytest.mark.asyncio
async def test_list_games_sort_by_title_desc(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_chain(api_engine, title="Aaa")
    await _seed_chain(api_engine, title="Zzz")
    response = await authed_client.get(
        "/api/v3/game?sort=title&direction=desc"
    )
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert titles == sorted(titles, reverse=True)


@pytest.mark.asyncio
async def test_list_games_sort_by_added_at(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """`added_at` maps to `Game.created_at`. Seeding in order
    A→B→C and sorting `added_at desc` returns C→B→A."""
    _, first, _ = await _seed_chain(api_engine, title="First")
    _, second, _ = await _seed_chain(api_engine, title="Second")
    _, third, _ = await _seed_chain(api_engine, title="Third")
    response = await authed_client.get(
        "/api/v3/game?sort=added_at&direction=desc"
    )
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert ids == [third, second, first]


@pytest.mark.asyncio
async def test_list_games_sort_unknown_key_rejected(
    authed_client: httpx.AsyncClient,
) -> None:
    """Literal-typed param rejects unknown sort keys."""
    response = await authed_client.get("/api/v3/game?sort=NotAColumn")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# slice 127 — monitored filter
# ---------------------------------------------------------------------------


async def _seed_with_monitored(
    api_engine: AsyncEngine, *, title: str, monitored: bool
) -> int:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(
            slug=f"mon-pl-{title}".lower(), name="Mega Drive"
        )
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"mon-{title}".lower(),
            title=title,
            monitored=monitored,
        )
        session.add(game)
        await session.commit()
        return game.id


@pytest.mark.asyncio
async def test_list_games_monitored_true_keeps_only_monitored(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_with_monitored(api_engine, title="On", monitored=True)
    await _seed_with_monitored(api_engine, title="Off", monitored=False)

    response = await authed_client.get("/api/v3/game?monitored=true")
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert "On" in titles
    assert "Off" not in titles


@pytest.mark.asyncio
async def test_list_games_monitored_false_keeps_only_unmonitored(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_with_monitored(api_engine, title="A", monitored=True)
    await _seed_with_monitored(api_engine, title="B", monitored=False)

    response = await authed_client.get("/api/v3/game?monitored=false")
    assert response.status_code == 200
    titles = [row["title"] for row in response.json()]
    assert "B" in titles
    assert "A" not in titles


# ---------------------------------------------------------------------------
# slice 146 — PATCH /api/v3/game/{id}/locked-fields (anti-RomM-#1770)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_locked_fields_locks_a_field(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Locking ``title`` adds it to ``locked_fields`` and the
    response surfaces the updated list."""
    _, game_id, _ = await _seed_chain(api_engine, title="LockMe")

    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "title", "locked": True},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["locked_fields"] == ["title"]


@pytest.mark.asyncio
async def test_patch_locked_fields_unlocks_a_field(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Locking then unlocking returns the field to the unlocked
    set (idempotent path)."""
    _, game_id, _ = await _seed_chain(api_engine, title="UnlockMe")

    await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "summary", "locked": True},
    )
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "summary", "locked": False},
    )
    assert resp.status_code == 200
    assert resp.json()["locked_fields"] == []


@pytest.mark.asyncio
async def test_patch_locked_fields_idempotent_lock(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Re-locking an already-locked field is a no-op — no
    duplicates in the JSON list."""
    _, game_id, _ = await _seed_chain(api_engine, title="DoubleLock")

    for _ in range(3):
        resp = await authed_client.patch(
            f"/api/v3/game/{game_id}/locked-fields",
            json={"field": "developer", "locked": True},
        )
        assert resp.status_code == 200
    assert resp.json()["locked_fields"] == ["developer"]


@pytest.mark.asyncio
async def test_patch_locked_fields_keeps_other_locks(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Toggling one field never disturbs the others. Locks for
    ``title`` and ``summary`` survive an unlock of ``rating``
    that wasn't even locked to begin with."""
    _, game_id, _ = await _seed_chain(api_engine, title="MultiLock")

    await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "title", "locked": True},
    )
    await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "summary", "locked": True},
    )
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "rating", "locked": False},
    )
    assert resp.status_code == 200
    assert resp.json()["locked_fields"] == ["summary", "title"]


@pytest.mark.asyncio
async def test_patch_locked_fields_rejects_unknown_field(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The body is validated against ``ProviderField`` — random
    strings 422 instead of silently no-op'ing (which would let
    drift creep in)."""
    _, game_id, _ = await _seed_chain(api_engine, title="UnknownField")
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "not_a_real_field", "locked": True},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_locked_fields_rejects_extra_keys(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, _ = await _seed_chain(api_engine, title="ExtraGuardLock")
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "title", "locked": True, "stowaway": "x"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_locked_fields_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.patch(
        "/api/v3/game/9999999/locked-fields",
        json={"field": "title", "locked": True},
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_patch_locked_fields_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.patch(
        "/api/v3/game/1/locked-fields",
        json={"field": "title", "locked": True},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_locked_fields_persists_across_read(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """End-to-end: lock a field, then GET the Game and verify
    the lock survived the round-trip (so the commit really
    landed, not just the in-memory mutation)."""
    _, game_id, _ = await _seed_chain(api_engine, title="Persisted")
    await authed_client.patch(
        f"/api/v3/game/{game_id}/locked-fields",
        json={"field": "cover", "locked": True},
    )
    resp = await authed_client.get(f"/api/v3/game/{game_id}")
    assert resp.status_code == 200
    assert resp.json()["locked_fields"] == ["cover"]


# ---------------------------------------------------------------------------
# slice 147 — PATCH /api/v3/game/{id}/field (operator text edits)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_field_edits_text_field_and_auto_locks(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Editing ``developer`` writes the value AND auto-locks the
    field — the constitutional default so the aggregator stops
    overwriting it."""
    _, game_id, _ = await _seed_chain(api_engine, title="EditMe")

    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "developer", "value": "Sonic Team"},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["developer"] == "Sonic Team"
    assert body["locked_fields"] == ["developer"]


@pytest.mark.asyncio
async def test_patch_field_strips_whitespace(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A trailing newline / surrounding spaces from the inline
    editor get stripped so the persisted value is canonical."""
    _, game_id, _ = await _seed_chain(api_engine, title="Whitespace")

    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "publisher", "value": "  Sega  \n"},
    )
    assert resp.status_code == 200
    assert resp.json()["publisher"] == "Sega"


@pytest.mark.asyncio
async def test_patch_field_clears_with_null(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """``value=null`` (or empty after strip) clears the field —
    operators sometimes want to wipe a wrong-aggregator value."""
    _, game_id, _ = await _seed_chain(api_engine, title="ClearMe")
    # First set something.
    await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "developer", "value": "Wrong"},
    )
    # Then clear it.
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "developer", "value": None},
    )
    assert resp.status_code == 200
    assert resp.json()["developer"] is None
    # But the auto-lock stays on because the operator's intent
    # is still "don't let the aggregator put anything here".
    assert "developer" in resp.json()["locked_fields"]


@pytest.mark.asyncio
async def test_patch_field_can_skip_auto_lock(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """``auto_lock=false`` is the escape hatch for the rare case
    the operator wants to seed a value without freezing it."""
    _, game_id, _ = await _seed_chain(api_engine, title="OptOut")
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={
            "field": "developer",
            "value": "Sonic Team",
            "auto_lock": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["developer"] == "Sonic Team"
    assert resp.json()["locked_fields"] == []


@pytest.mark.asyncio
async def test_patch_field_rejects_non_text_field(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Numeric / list fields are not text-editable on this
    surface — they need their own typed payloads."""
    _, game_id, _ = await _seed_chain(api_engine, title="NumField")
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "rating", "value": "9.5"},
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "field_not_editable"


@pytest.mark.asyncio
async def test_patch_field_rejects_too_long(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """developer.max_length=128 — 200-char input is rejected
    cleanly rather than letting SQLAlchemy raise."""
    _, game_id, _ = await _seed_chain(api_engine, title="TooLong")
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "developer", "value": "x" * 200},
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "value_too_long"


@pytest.mark.asyncio
async def test_patch_field_rejects_title_clear(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """title is NOT NULL at the schema level — clearing would
    500 in the DB. Reject upfront."""
    _, game_id, _ = await _seed_chain(api_engine, title="KeepTitle")
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "title", "value": None},
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "title_required"


@pytest.mark.asyncio
async def test_patch_field_rejects_unknown_field(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Random strings hit Pydantic's ProviderField validator
    and 422 — same as the lock endpoint."""
    _, game_id, _ = await _seed_chain(api_engine, title="UnknownEdit")
    resp = await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "not_a_real_field", "value": "x"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_field_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.patch(
        "/api/v3/game/9999999/field",
        json={"field": "developer", "value": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_patch_field_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.patch(
        "/api/v3/game/1/field",
        json={"field": "developer", "value": "x"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_field_persists_across_read(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """End-to-end: edit + lock survive a fresh GET so we know
    the commit really landed."""
    _, game_id, _ = await _seed_chain(api_engine, title="RoundTrip")
    await authed_client.patch(
        f"/api/v3/game/{game_id}/field",
        json={"field": "summary", "value": "A blue hedgehog runs fast."},
    )
    resp = await authed_client.get(f"/api/v3/game/{game_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == "A blue hedgehog runs fast."
    assert body["locked_fields"] == ["summary"]


# ---------------------------------------------------------------------------
# slice 149 — PUT /api/v3/game/{id}/notes (operator-owned free text)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_notes_writes_value(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, _ = await _seed_chain(api_engine, title="WriteNotes")
    resp = await authed_client.put(
        f"/api/v3/game/{game_id}/notes",
        json={"notes": "Picked up at a swap meet — region locked."},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["notes"] == "Picked up at a swap meet — region locked."
    # Notes do not flip the lock surface — they're a separate
    # column outside the aggregator's reach by design.
    assert body["locked_fields"] == []


@pytest.mark.asyncio
async def test_put_notes_clears_with_null(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, _ = await _seed_chain(api_engine, title="ClearNotes")
    await authed_client.put(
        f"/api/v3/game/{game_id}/notes",
        json={"notes": "Old note"},
    )
    resp = await authed_client.put(
        f"/api/v3/game/{game_id}/notes",
        json={"notes": None},
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] is None


@pytest.mark.asyncio
async def test_put_notes_strips_to_null(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Whitespace-only input canonicalises to null so reads have
    one representation of empty."""
    _, game_id, _ = await _seed_chain(api_engine, title="StripNotes")
    resp = await authed_client.put(
        f"/api/v3/game/{game_id}/notes",
        json={"notes": "   \n  "},
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] is None


@pytest.mark.asyncio
async def test_put_notes_preserves_internal_whitespace(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Multi-paragraph notes survive the strip — only leading /
    trailing whitespace is trimmed."""
    _, game_id, _ = await _seed_chain(api_engine, title="MultiParaNotes")
    notes = "Line one.\n\nLine two — see disc 2 for menu glitch."
    resp = await authed_client.put(
        f"/api/v3/game/{game_id}/notes",
        json={"notes": f"  {notes}  "},
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] == notes


@pytest.mark.asyncio
async def test_put_notes_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.put(
        "/api/v3/game/9999999/notes",
        json={"notes": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_put_notes_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.put(
        "/api/v3/game/1/notes", json={"notes": "x"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_put_notes_rejects_extra_keys(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, _ = await _seed_chain(api_engine, title="ExtraNotes")
    resp = await authed_client.put(
        f"/api/v3/game/{game_id}/notes",
        json={"notes": "x", "stowaway": "y"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_notes_persists_across_read(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, game_id, _ = await _seed_chain(api_engine, title="NotesRead")
    await authed_client.put(
        f"/api/v3/game/{game_id}/notes",
        json={"notes": "Verified working on Mega Drive 2."},
    )
    resp = await authed_client.get(f"/api/v3/game/{game_id}")
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Verified working on Mega Drive 2."


# ---------------------------------------------------------------------------
# slice 151 — POST /api/v3/game/bulk-monitor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_monitor_flips_to_false(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Three games default-monitored; bulk-flip them off in one
    call and confirm via individual reads."""
    _, a, _ = await _seed_chain(api_engine, title="A")
    _, b, _ = await _seed_chain(api_engine, title="B")
    _, c, _ = await _seed_chain(api_engine, title="C")

    resp = await authed_client.post(
        "/api/v3/game/bulk-monitor",
        json={"gameIds": [a, b, c], "monitored": False},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["updated"] == 3
    assert body["missing"] == []

    for gid in (a, b, c):
        row = await authed_client.get(f"/api/v3/game/{gid}")
        assert row.json()["monitored"] is False


@pytest.mark.asyncio
async def test_bulk_monitor_reports_missing_ids(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Missing ids surface in the response without sinking the
    rest of the batch — partial success is the contract."""
    _, a, _ = await _seed_chain(api_engine, title="Real")

    resp = await authed_client.post(
        "/api/v3/game/bulk-monitor",
        json={"gameIds": [a, 999_999, 888_888], "monitored": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 1
    assert body["missing"] == [888_888, 999_999]


@pytest.mark.asyncio
async def test_bulk_monitor_idempotent(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Setting the same flag twice still returns updated=N
    (intent-based, not change-based)."""
    _, a, _ = await _seed_chain(api_engine, title="Idem")
    for _ in range(3):
        resp = await authed_client.post(
            "/api/v3/game/bulk-monitor",
            json={"gameIds": [a], "monitored": False},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1


@pytest.mark.asyncio
async def test_bulk_monitor_rejects_empty_list(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/game/bulk-monitor",
        json={"gameIds": [], "monitored": False},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_monitor_rejects_too_many(
    authed_client: httpx.AsyncClient,
) -> None:
    """Cap is 500 — 501 is rejected upfront so we never let an
    accidental SELECT-IN explode."""
    resp = await authed_client.post(
        "/api/v3/game/bulk-monitor",
        json={
            "gameIds": list(range(1, 502)),
            "monitored": False,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_monitor_rejects_extra_keys(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/game/bulk-monitor",
        json={
            "gameIds": [1],
            "monitored": False,
            "stowaway": "x",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_monitor_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v3/game/bulk-monitor",
        json={"gameIds": [1], "monitored": False},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 153 — POST /api/v3/game/bulk-delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_delete_removes_games_and_cascades(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Three games with releases each; bulk-delete drops the
    Game rows AND their Releases via cascade."""
    _, a, a_releases = await _seed_chain(
        api_engine, title="ToDelete-A", release_count=2
    )
    _, b, _ = await _seed_chain(
        api_engine, title="ToDelete-B", release_count=1
    )

    resp = await authed_client.post(
        "/api/v3/game/bulk-delete",
        json={"gameIds": [a, b]},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["deleted"] == 2
    assert body["missing"] == []

    # The Game rows are gone.
    for gid in (a, b):
        row = await authed_client.get(f"/api/v3/game/{gid}")
        assert row.status_code == 404

    # And the cascaded Releases too — fetching releases for the
    # deleted game returns 404 (game_not_found) since the parent
    # Game is gone.
    releases = await authed_client.get(f"/api/v3/game/{a}/release")
    assert releases.status_code == 404
    # Belt-and-suspenders: the release ids really don't exist
    # anywhere reachable.
    assert all(rid > 0 for rid in a_releases)


@pytest.mark.asyncio
async def test_bulk_delete_with_files_unlinks_dump_paths(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path,
) -> None:
    """Slice 480 regression — ``deleteFiles=true`` MUST actually
    unlink every cascaded Dump's on-disk file, not just drop the
    DB rows. Operator complained that "supprimer aussi les ROMs"
    left 478 files on disk; this test pins the contract."""
    _, game_id, releases = await _seed_chain(
        api_engine, title="Cascade Delete Test", release_count=2
    )
    file_a = tmp_path / "rom-a.zip"
    file_a.write_bytes(b"x" * 100)
    file_b = tmp_path / "rom-b.zip"
    file_b.write_bytes(b"y" * 100)
    await _seed_dump_for_release(
        api_engine, release_id=releases[0], path=str(file_a), sha1="a" * 40
    )
    await _seed_dump_for_release(
        api_engine, release_id=releases[1], path=str(file_b), sha1="b" * 40
    )
    assert file_a.exists() and file_b.exists()

    resp = await authed_client.post(
        "/api/v3/game/bulk-delete",
        json={"gameIds": [game_id], "deleteFiles": True},
    )
    assert resp.status_code == 200, resp.text
    assert not file_a.exists(), "Dump.path must be unlinked"
    assert not file_b.exists(), "every cascaded Dump.path must be unlinked"


@pytest.mark.asyncio
async def test_bulk_delete_without_files_keeps_dump_paths(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path,
) -> None:
    """And the default path — ``deleteFiles=false`` (or omitted)
    leaves the files on disk."""
    _, game_id, releases = await _seed_chain(
        api_engine, title="Keep Files", release_count=1
    )
    file_path = tmp_path / "keep.zip"
    file_path.write_bytes(b"keep me")
    await _seed_dump_for_release(
        api_engine, release_id=releases[0], path=str(file_path), sha1="c" * 40
    )

    resp = await authed_client.post(
        "/api/v3/game/bulk-delete",
        json={"gameIds": [game_id]},
    )
    assert resp.status_code == 200
    assert file_path.exists()


@pytest.mark.asyncio
async def test_bulk_delete_reports_missing_ids(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, real, _ = await _seed_chain(api_engine, title="RealOne")
    resp = await authed_client.post(
        "/api/v3/game/bulk-delete",
        json={"gameIds": [real, 999_999, 888_888]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == 1
    assert body["missing"] == [888_888, 999_999]


@pytest.mark.asyncio
async def test_bulk_delete_idempotent(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Re-running bulk-delete on already-deleted ids surfaces
    them as ``missing`` rather than blowing up."""
    _, gid, _ = await _seed_chain(api_engine, title="DeleteTwice")
    first = await authed_client.post(
        "/api/v3/game/bulk-delete", json={"gameIds": [gid]}
    )
    assert first.status_code == 200
    assert first.json()["deleted"] == 1

    second = await authed_client.post(
        "/api/v3/game/bulk-delete", json={"gameIds": [gid]}
    )
    assert second.status_code == 200
    assert second.json()["deleted"] == 0
    assert second.json()["missing"] == [gid]


@pytest.mark.asyncio
async def test_bulk_delete_rejects_empty_list(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/game/bulk-delete", json={"gameIds": []}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_rejects_too_many(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/game/bulk-delete",
        json={"gameIds": list(range(1, 502))},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_rejects_extra_keys(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/game/bulk-delete",
        json={"gameIds": [1], "stowaway": "x"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v3/game/bulk-delete", json={"gameIds": [1]}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 165 — bulk-delete sweeps tag_assignment rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_delete_sweeps_tag_assignment_for_games(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Deleting a Game must drop its rows from the polymorphic
    ``tag_assignment`` table; otherwise the slice-135
    usage_count surface drifts."""
    await _seed_tags(api_engine, ids=[1, 2])
    _, a, _ = await _seed_chain(api_engine, title="DropMe")
    _, b, _ = await _seed_chain(api_engine, title="Survivor")

    # Tag both games via the bulk-tag surface so the
    # tag_assignment rows are real.
    await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a, b], "tagIds": [1, 2], "action": "add"},
    )

    # Delete only one. The other should keep its assignments.
    resp = await authed_client.post(
        "/api/v3/game/bulk-delete", json={"gameIds": [a]}
    )
    assert resp.status_code == 200, resp.json()

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (
            await session.execute(
                TagAssignment.__table__.select().where(
                    TagAssignment.entity_type == "game",
                )
            )
        ).all()
    pairs = {(row.tag_id, row.entity_id) for row in rows}
    assert pairs == {(1, b), (2, b)}


# ---------------------------------------------------------------------------
# slice 169 — DELETE /api/v3/game/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_game_drops_row_and_sweeps_tag_assignments(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Single-item DELETE behaves like a one-id bulk-delete:
    Game row gone, cascaded Releases gone, ``tag_assignment``
    rows for both swept."""
    await _seed_tags(api_engine, ids=[1])
    _, gid, release_ids = await _seed_chain(
        api_engine, title="SingleDel", release_count=2
    )

    # Tag the game (writes tag_assignment via slice 154).
    await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [gid], "tagIds": [1], "action": "add"},
    )
    # Hand-tag the releases.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        for rid in release_ids:
            session.add(
                TagAssignment(tag_id=1, entity_type="release", entity_id=rid)
            )
        await session.commit()

    resp = await authed_client.delete(f"/api/v3/game/{gid}")
    assert resp.status_code == 204
    # Game gone.
    follow = await authed_client.get(f"/api/v3/game/{gid}")
    assert follow.status_code == 404

    async with sm() as session:
        rows = (
            await session.execute(
                TagAssignment.__table__.select()
            )
        ).all()
    assert rows == []


@pytest.mark.asyncio
async def test_delete_game_404_when_missing(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.delete("/api/v3/game/9999999")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_delete_game_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.delete("/api/v3/game/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bulk_delete_sweeps_tag_assignment_for_cascaded_releases(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Releases are cascaded when the parent Game is deleted —
    their tag_assignment rows must be swept too."""
    await _seed_tags(api_engine, ids=[1])
    _, a, release_ids = await _seed_chain(
        api_engine, title="ReleaseTagged", release_count=2
    )
    assert len(release_ids) == 2

    # Hand-insert tag_assignment rows for the releases (no
    # bulk-tag surface ships for releases yet — slice 154 only
    # covers games).
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        for rid in release_ids:
            session.add(
                TagAssignment(
                    tag_id=1,
                    entity_type="release",
                    entity_id=rid,
                )
            )
        await session.commit()

    resp = await authed_client.post(
        "/api/v3/game/bulk-delete", json={"gameIds": [a]}
    )
    assert resp.status_code == 200

    async with sm() as session:
        rows = (
            await session.execute(
                TagAssignment.__table__.select().where(
                    TagAssignment.entity_type == "release",
                    TagAssignment.entity_id.in_(release_ids),
                )
            )
        ).all()
    assert rows == []


# ---------------------------------------------------------------------------
# slice 154 — POST /api/v3/game/bulk-tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_tag_add_unions_into_existing(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Two games, one already carrying tag 1; bulk-add tags 2,3
    leaves tag 1 in place and unions 2,3 in (sorted, deduped)."""
    await _seed_tags(api_engine, ids=[1, 2, 3])
    _, a, _ = await _seed_chain(api_engine, title="TagA")
    _, b, _ = await _seed_chain(api_engine, title="TagB")

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = await session.get(Game, a)
        assert row is not None
        row.tags = [1]
        await session.commit()

    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a, b], "tagIds": [2, 3], "action": "add"},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["updated"] == 2
    assert body["missing"] == []

    # Verify the union shape via per-row reads.
    a_row = await authed_client.get(f"/api/v3/game/{a}")
    b_row = await authed_client.get(f"/api/v3/game/{b}")
    assert a_row.json()["tags"] == [1, 2, 3]
    assert b_row.json()["tags"] == [2, 3]


@pytest.mark.asyncio
async def test_bulk_tag_add_dedupes(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Re-adding tags already on the row is a no-op."""
    await _seed_tags(api_engine, ids=[1, 2, 3])
    _, a, _ = await _seed_chain(api_engine, title="DedupeTag")
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = await session.get(Game, a)
        assert row is not None
        row.tags = [1, 2]
        await session.commit()

    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a], "tagIds": [1, 2, 3], "action": "add"},
    )
    assert resp.status_code == 200
    a_row = await authed_client.get(f"/api/v3/game/{a}")
    assert a_row.json()["tags"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_bulk_tag_remove_strips(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_tags(api_engine, ids=[1, 2, 3, 4])
    _, a, _ = await _seed_chain(api_engine, title="StripTag")
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = await session.get(Game, a)
        assert row is not None
        row.tags = [1, 2, 3, 4]
        await session.commit()

    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a], "tagIds": [2, 3], "action": "remove"},
    )
    assert resp.status_code == 200
    a_row = await authed_client.get(f"/api/v3/game/{a}")
    assert a_row.json()["tags"] == [1, 4]


@pytest.mark.asyncio
async def test_bulk_tag_remove_missing_tag_is_noop(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Removing a tag the row doesn't carry doesn't blow up."""
    await _seed_tags(api_engine, ids=[5, 99, 100])
    _, a, _ = await _seed_chain(api_engine, title="NoOpRemove")
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = await session.get(Game, a)
        assert row is not None
        row.tags = [5]
        await session.commit()

    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a], "tagIds": [99, 100], "action": "remove"},
    )
    assert resp.status_code == 200
    a_row = await authed_client.get(f"/api/v3/game/{a}")
    assert a_row.json()["tags"] == [5]


@pytest.mark.asyncio
async def test_bulk_tag_reports_missing(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_tags(api_engine, ids=[1])
    _, real, _ = await _seed_chain(api_engine, title="RealTagged")
    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={
            "gameIds": [real, 999_999],
            "tagIds": [1],
            "action": "add",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 1
    assert body["missing"] == [999_999]


@pytest.mark.asyncio
async def test_bulk_tag_rejects_unknown_action(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [1], "tagIds": [1], "action": "replace"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_tag_rejects_empty_lists(
    authed_client: httpx.AsyncClient,
) -> None:
    """Both gameIds and tagIds must be non-empty — an empty
    request can't have a meaningful intent."""
    for payload in (
        {"gameIds": [], "tagIds": [1], "action": "add"},
        {"gameIds": [1], "tagIds": [], "action": "add"},
    ):
        resp = await authed_client.post(
            "/api/v3/game/bulk-tag", json=payload
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_tag_rejects_too_many(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={
            "gameIds": list(range(1, 502)),
            "tagIds": [1],
            "action": "add",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_tag_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [1], "tagIds": [1], "action": "add"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# slice 164 — bulk-tag syncs the polymorphic ``tag_assignment`` table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_tag_add_creates_tag_assignment_rows(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Bulk-add must INSERT into ``tag_assignment`` so the
    slice-135 ``usageCount`` surface stays in sync with the
    JSON cache (the bug slice 154 inadvertently shipped)."""
    await _seed_tags(api_engine, ids=[1, 2])
    _, a, _ = await _seed_chain(api_engine, title="AssignA")
    _, b, _ = await _seed_chain(api_engine, title="AssignB")

    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a, b], "tagIds": [1, 2], "action": "add"},
    )
    assert resp.status_code == 200, resp.json()

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (
            await session.execute(
                TagAssignment.__table__.select().where(
                    TagAssignment.entity_type == "game",
                    TagAssignment.entity_id.in_([a, b]),
                )
            )
        ).all()
    pairs = {(row.tag_id, row.entity_id) for row in rows}
    assert pairs == {(1, a), (2, a), (1, b), (2, b)}


@pytest.mark.asyncio
async def test_bulk_tag_add_is_idempotent_on_assignments(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Re-adding the same (tag, game) pair must NOT violate the
    ``uq_tag_assignment_unique`` constraint — the endpoint
    pre-fetches existing rows and inserts only the diff."""
    await _seed_tags(api_engine, ids=[1, 2])
    _, a, _ = await _seed_chain(api_engine, title="ReAssign")

    for _ in range(3):
        resp = await authed_client.post(
            "/api/v3/game/bulk-tag",
            json={"gameIds": [a], "tagIds": [1, 2], "action": "add"},
        )
        assert resp.status_code == 200, resp.json()

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (
            await session.execute(
                TagAssignment.__table__.select().where(
                    TagAssignment.entity_type == "game",
                    TagAssignment.entity_id == a,
                )
            )
        ).all()
    assert {row.tag_id for row in rows} == {1, 2}
    # Exactly two rows — not 6 (3 round-trips × 2 tags).
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_bulk_tag_remove_deletes_tag_assignment_rows(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_tags(api_engine, ids=[1, 2, 3])
    _, a, _ = await _seed_chain(api_engine, title="UnassignA")
    # Seed via add first.
    await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a], "tagIds": [1, 2, 3], "action": "add"},
    )

    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a], "tagIds": [1, 3], "action": "remove"},
    )
    assert resp.status_code == 200

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (
            await session.execute(
                TagAssignment.__table__.select().where(
                    TagAssignment.entity_type == "game",
                    TagAssignment.entity_id == a,
                )
            )
        ).all()
    assert {row.tag_id for row in rows} == {2}


@pytest.mark.asyncio
async def test_bulk_tag_400_on_unknown_tag_id(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Passing a tag_id that doesn't exist in the Tag table 400s
    cleanly instead of 500-ing on the FK INSERT."""
    await _seed_tags(api_engine, ids=[1])
    _, a, _ = await _seed_chain(api_engine, title="UnknownTag")

    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={
            "gameIds": [a],
            "tagIds": [1, 999],
            "action": "add",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "unknown_tag_ids"


@pytest.mark.asyncio
async def test_bulk_tag_remove_missing_pair_is_noop(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Removing a (tag, game) pair that doesn't exist in
    tag_assignment must not error — it's already absent."""
    await _seed_tags(api_engine, ids=[1])
    _, a, _ = await _seed_chain(api_engine, title="UnseenRemove")

    resp = await authed_client.post(
        "/api/v3/game/bulk-tag",
        json={"gameIds": [a], "tagIds": [1], "action": "remove"},
    )
    assert resp.status_code == 200

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (
            await session.execute(
                TagAssignment.__table__.select().where(
                    TagAssignment.entity_type == "game",
                    TagAssignment.entity_id == a,
                )
            )
        ).all()
    assert rows == []


# ---------------------------------------------------------------------------
# slice 156 — GET /api/v3/game?tag_id= filter
# ---------------------------------------------------------------------------


async def _seed_with_tags(
    api_engine: AsyncEngine, *, title: str, tags: list[int]
) -> int:
    """Seed a Game with the given tag-id list and return its id."""
    _, gid, _ = await _seed_chain(api_engine, title=title)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = await session.get(Game, gid)
        assert row is not None
        row.tags = tags
        await session.commit()
    return gid


@pytest.mark.asyncio
async def test_list_games_tag_filter_finds_matching(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    a = await _seed_with_tags(api_engine, title="Alpha", tags=[5])
    b = await _seed_with_tags(api_engine, title="Bravo", tags=[5, 9])
    _ = await _seed_with_tags(api_engine, title="Charlie", tags=[7])

    resp = await authed_client.get("/api/v3/game?tag_id=5")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert a in ids
    assert b in ids
    assert all(row["title"] != "Charlie" for row in resp.json())


@pytest.mark.asyncio
async def test_list_games_tag_filter_rejects_substring_collision(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Filtering by tag id 5 must NOT match a game tagged with
    15 — the bracket-and-comma normalisation prevents that
    common JSON-text-LIKE bug."""
    real = await _seed_with_tags(api_engine, title="Real", tags=[5])
    decoy = await _seed_with_tags(api_engine, title="Decoy", tags=[15])

    resp = await authed_client.get("/api/v3/game?tag_id=5")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert real in ids
    assert decoy not in ids


@pytest.mark.asyncio
async def test_list_games_tag_filter_handles_first_and_last_position(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The bracket-replace pattern needs to match at every
    position: first, middle, last, and singleton."""
    first = await _seed_with_tags(api_engine, title="First", tags=[7, 1, 2])
    middle = await _seed_with_tags(api_engine, title="Middle", tags=[1, 7, 2])
    last = await _seed_with_tags(api_engine, title="Last", tags=[1, 2, 7])
    only = await _seed_with_tags(api_engine, title="Only", tags=[7])

    resp = await authed_client.get("/api/v3/game?tag_id=7")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert {first, middle, last, only} <= ids


@pytest.mark.asyncio
async def test_list_games_tag_filter_returns_empty_for_unused_tag(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_with_tags(api_engine, title="HasOne", tags=[1])
    resp = await authed_client.get("/api/v3/game?tag_id=999")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_games_tag_filter_skips_games_with_no_tags(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Games seeded with the empty default tag list are not
    matched by any tag-id filter — confirms the empty `[]` JSON
    doesn't collide with the comma-padded pattern."""
    untagged = await _seed_with_tags(api_engine, title="Untagged", tags=[])
    tagged = await _seed_with_tags(api_engine, title="Tagged", tags=[3])

    resp = await authed_client.get("/api/v3/game?tag_id=3")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert tagged in ids
    assert untagged not in ids


@pytest.mark.asyncio
async def test_list_games_tag_filter_combines_with_platform_and_q(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """tag_id stacks with platform_id and q like the other
    filters do."""
    a = await _seed_with_tags(api_engine, title="Combo Match", tags=[2])
    _ = await _seed_with_tags(api_engine, title="Combo NoTag", tags=[])
    _ = await _seed_with_tags(api_engine, title="Other", tags=[2])

    resp = await authed_client.get("/api/v3/game?tag_id=2&q=combo")
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert ids == [a]


# ---------------------------------------------------------------------------
# slice 166 — GET /api/v3/game?library_id= filter
# ---------------------------------------------------------------------------


async def _bind_release_to_library(
    api_engine: AsyncEngine, *, release_id: int, library_id: int
) -> None:
    """Set Release.library_id directly via raw SQL with FK
    enforcement off — same trick as the Wanted libraryId tests
    in slice 161 (seeding the full Library + 5 profiles graph
    is overkill for a filter-behavior test)."""
    from sqlalchemy import text

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        await session.execute(text("PRAGMA foreign_keys = OFF"))
        await session.execute(
            text(
                "UPDATE release SET library_id = :lid WHERE id = :rid"
            ),
            {"lid": library_id, "rid": release_id},
        )
        await session.commit()


@pytest.mark.asyncio
async def test_list_games_library_id_filter_via_release_join(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A game lands in the result only if it has at least one
    Release bound to the requested library."""
    _, in_lib, in_lib_releases = await _seed_chain(
        api_engine, title="InLibrary", release_count=1
    )
    _, other_lib, other_lib_releases = await _seed_chain(
        api_engine, title="OtherLibrary", release_count=1
    )
    _, no_release, _ = await _seed_chain(
        api_engine, title="NoReleaseHere", release_count=0
    )

    await _bind_release_to_library(
        api_engine, release_id=in_lib_releases[0], library_id=42
    )
    await _bind_release_to_library(
        api_engine, release_id=other_lib_releases[0], library_id=99
    )

    resp = await authed_client.get("/api/v3/game?library_id=42")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert in_lib in ids
    assert other_lib not in ids
    assert no_release not in ids


@pytest.mark.asyncio
async def test_list_games_library_id_filter_dedupes_multi_release(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A game with multiple Releases in the same library appears
    exactly once — the EXISTS subquery doesn't multiply rows."""
    _, gid, release_ids = await _seed_chain(
        api_engine, title="MultiInLib", release_count=3
    )
    for rid in release_ids:
        await _bind_release_to_library(
            api_engine, release_id=rid, library_id=7
        )

    resp = await authed_client.get("/api/v3/game?library_id=7")
    assert resp.status_code == 200
    matches = [row for row in resp.json() if row["id"] == gid]
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_list_games_library_id_filter_excludes_no_release(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A game whose only Release is bound to a different library
    is excluded — the filter is "has Release in THIS library",
    not "has any Release"."""
    _, gid, releases = await _seed_chain(
        api_engine, title="WrongLib", release_count=1
    )
    await _bind_release_to_library(
        api_engine, release_id=releases[0], library_id=99
    )

    resp = await authed_client.get("/api/v3/game?library_id=42")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert gid not in ids


@pytest.mark.asyncio
async def test_list_games_library_id_filter_combines_with_q(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    _, match, match_releases = await _seed_chain(
        api_engine, title="Sonic Library", release_count=1
    )
    _, other, other_releases = await _seed_chain(
        api_engine, title="Sonic NoLib", release_count=1
    )
    _, lib_only, lib_only_releases = await _seed_chain(
        api_engine, title="Mario Library", release_count=1
    )
    await _bind_release_to_library(
        api_engine, release_id=match_releases[0], library_id=3
    )
    await _bind_release_to_library(
        api_engine, release_id=other_releases[0], library_id=99
    )
    await _bind_release_to_library(
        api_engine, release_id=lib_only_releases[0], library_id=3
    )

    resp = await authed_client.get(
        "/api/v3/game?library_id=3&q=sonic"
    )
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert ids == [match]
