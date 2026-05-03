"""Game + Release read-endpoint tests (slice 86)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import Dump, Game, Platform, Release
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
