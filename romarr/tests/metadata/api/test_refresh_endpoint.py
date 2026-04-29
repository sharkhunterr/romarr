"""POST /api/v3/game/{id}/refresh-metadata tests (T058).

Exercises the full IGDB → cache → aggregator → Game-persistence path
end-to-end through the FastAPI app. Twitch OAuth + IGDB API are
mocked via respx.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password
from romarr.domain.models import Game, Platform
from romarr.metadata.encryption import encrypt
from romarr.metadata.models import FieldPriority, MetadataProviderConfig
from tests.metadata.api.conftest import seed_provider_rows


async def _seed_admin_and_login(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="admin",
                role=ROLE_ADMIN,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert response.status_code == 204


async def _seed_game(api_engine: AsyncEngine) -> int:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(slug="megadrive", name="Mega Drive", igdb_id=29)
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug="sonic-1",
            title="Sonic the Hedgehog",
        )
        session.add(game)
        await session.commit()
        await session.refresh(game)
        return game.id


async def _enable_igdb(api_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(
                select(MetadataProviderConfig).where(
                    MetadataProviderConfig.provider_name == "igdb"
                )
            )
        ).scalar_one()
        row.enabled = True
        row.config_encrypted = encrypt(
            json.dumps({"client_id": "id-1", "client_secret": "shh"}).encode()
        )
        await session.commit()


async def _seed_field_priority_minimal(api_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sm() as session:
        for field, order in [("title", 1), ("summary", 1), ("rating", 1)]:
            session.add(
                FieldPriority(
                    field_name=field,
                    provider_name="igdb",
                    priority_order=order,
                    updated_at=now,
                )
            )
        await session.commit()


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post("/api/v3/game/1/refresh-metadata")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_unknown_game_returns_404(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    await seed_provider_rows(api_engine)
    await _seed_admin_and_login(api_engine, api_client)
    response = await api_client.post("/api/v3/game/9999/refresh-metadata")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# End-to-end refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_populates_game_from_igdb(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    """End-to-end happy path: enable IGDB, mock Twitch + IGDB, hit
    /refresh-metadata, assert the Game's columns updated and the
    response carries per-field provenance."""
    await seed_provider_rows(api_engine)
    await _enable_igdb(api_engine)
    await _seed_field_priority_minimal(api_engine)
    game_id = await _seed_game(api_engine)
    await _seed_admin_and_login(api_engine, api_client)

    igdb_payload = [
        {
            "id": 1234,
            "name": "Sonic the Hedgehog",
            "summary": "Genesis classic.",
            "rating": 87.5,
        }
    ]

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "twitch-bearer", "expires_in": 3600}
            )
        )
        respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(200, json=igdb_payload)
        )

        response = await api_client.post(
            f"/api/v3/game/{game_id}/refresh-metadata"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["game_id"] == game_id
    assert body["needs_metadata_refresh"] is False
    assert body["fields"]["title"] == {
        "value": "Sonic the Hedgehog",
        "provider": "igdb",
    }
    assert body["fields"]["summary"]["value"] == "Genesis classic."
    assert body["fields"]["rating"]["value"] == 87.5

    # Verify the Game row was updated in DB.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        game = (
            await session.execute(select(Game).where(Game.id == game_id))
        ).scalar_one()
    assert game.summary == "Genesis classic."
    assert game.rating == 87.5
    assert game.needs_metadata_refresh is False


@pytest.mark.asyncio
async def test_refresh_respects_locked_fields(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    """The locked title MUST NOT be overwritten even when IGDB returns a
    different value (FR-010 / RomM-#1770 anti-bug)."""
    await seed_provider_rows(api_engine)
    await _enable_igdb(api_engine)
    await _seed_field_priority_minimal(api_engine)
    game_id = await _seed_game(api_engine)
    await _seed_admin_and_login(api_engine, api_client)

    # Lock the title and pre-populate it with the operator's preferred value.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        game = (
            await session.execute(select(Game).where(Game.id == game_id))
        ).scalar_one()
        game.title = "Operator's Preferred Title"
        game.locked_fields = ["title"]
        await session.commit()

    igdb_payload = [
        {
            "id": 1234,
            "name": "IGDB Title (would overwrite)",
            "summary": "IGDB summary.",
        }
    ]

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "twitch-bearer", "expires_in": 3600}
            )
        )
        respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(200, json=igdb_payload)
        )

        response = await api_client.post(
            f"/api/v3/game/{game_id}/refresh-metadata"
        )

    assert response.status_code == 200
    body = response.json()
    assert "title" in body["skipped_locked"]
    assert body["fields"]["summary"]["value"] == "IGDB summary."

    async with sm() as session:
        game = (
            await session.execute(select(Game).where(Game.id == game_id))
        ).scalar_one()
    assert game.title == "Operator's Preferred Title"


@pytest.mark.asyncio
async def test_refresh_with_disabled_provider_sets_refresh_flag(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    """Zero enabled providers → aggregator returns needs_metadata_refresh=True."""
    await seed_provider_rows(api_engine)
    await _seed_field_priority_minimal(api_engine)
    game_id = await _seed_game(api_engine)
    await _seed_admin_and_login(api_engine, api_client)

    response = await api_client.post(f"/api/v3/game/{game_id}/refresh-metadata")
    assert response.status_code == 200
    body = response.json()
    assert body["needs_metadata_refresh"] is True
    # FR-009 additive invariant: the existing title is carried forward
    # under the "<existing>" provenance marker because no provider
    # contributed and the field is not locked.
    assert body["fields"]["title"] == {
        "value": "Sonic the Hedgehog",
        "provider": "<existing>",
    }


@pytest.mark.asyncio
async def test_refresh_uses_cache_on_second_call(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    metadata_env: Any,
) -> None:
    """A second refresh within TTL must hit the cache only — no IGDB
    call. Verified by setting respx side_effect to "any second call
    on /games would fail" and asserting that doesn't happen."""
    await seed_provider_rows(api_engine)
    await _enable_igdb(api_engine)
    await _seed_field_priority_minimal(api_engine)
    game_id = await _seed_game(api_engine)
    await _seed_admin_and_login(api_engine, api_client)

    igdb_payload = [{"id": 1234, "name": "Sonic", "summary": "Classic."}]

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "t", "expires_in": 3600}
            )
        )
        games_route = respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(200, json=igdb_payload)
        )

        first = await api_client.post(
            f"/api/v3/game/{game_id}/refresh-metadata"
        )
        second = await api_client.post(
            f"/api/v3/game/{game_id}/refresh-metadata"
        )

    assert first.status_code == 200 and second.status_code == 200
    # IGDB makes two POSTs per refresh (search + get_game). The
    # second refresh hits the cache and issues ZERO further calls,
    # so total stays at 2 instead of 4.
    assert games_route.call_count == 2
