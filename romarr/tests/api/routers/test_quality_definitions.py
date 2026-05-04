"""Quality-definitions endpoint tests (slice 266).

Read-only summary at ``GET /api/v3/quality-definition`` — aggregates
``Platform → PlatformFormat`` rows for the Settings > Quality
Definitions UI page.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import Platform, PlatformFormat
from tests.api.test_auth_endpoints import _seed_admin_user


_seed_counter = 0


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


async def _seed_platform_with_formats(
    api_engine: AsyncEngine,
    *,
    name: str,
    formats: list[tuple[str, int | None, int | None]],
) -> int:
    """Seed one Platform + N PlatformFormat rows. ``formats`` is a
    list of ``(extension, min_size_bytes, max_size_bytes)`` tuples.
    Returns the new ``platform_id``."""
    global _seed_counter
    _seed_counter += 1
    suffix = _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(
            slug=f"test-platform-{suffix}",
            name=name,
        )
        session.add(platform)
        await session.flush()
        for ext, min_s, max_s in formats:
            session.add(
                PlatformFormat(
                    platform_id=platform.id,
                    extension=ext,
                    format_type="cartridge",
                    min_size_bytes=min_s,
                    max_size_bytes=max_s,
                )
            )
        await session.commit()
        return int(platform.id)


@pytest.mark.asyncio
async def test_lists_platforms_with_their_formats(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Each Platform appears with its PlatformFormat rows nested
    in ``formats``."""
    pid = await _seed_platform_with_formats(
        api_engine,
        name="Mega Drive",
        formats=[
            (".md", 256_000, 16_000_000),
            (".bin", 256_000, 16_000_000),
        ],
    )

    response = await authed_client.get("/api/v3/quality-definition")
    assert response.status_code == 200
    body = response.json()
    md_row = next((r for r in body if r["platform_id"] == pid), None)
    assert md_row is not None
    assert md_row["platform_name"] == "Mega Drive"
    assert {f["extension"] for f in md_row["formats"]} == {".md", ".bin"}


@pytest.mark.asyncio
async def test_format_carries_size_bounds(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Each PlatformFormat row keeps its min/max byte bounds."""
    pid = await _seed_platform_with_formats(
        api_engine,
        name="NES",
        formats=[(".nes", 16_384, 4_194_304)],
    )

    response = await authed_client.get("/api/v3/quality-definition")
    body = response.json()
    nes_row = next((r for r in body if r["platform_id"] == pid), None)
    assert nes_row is not None
    nes_format = nes_row["formats"][0]
    assert nes_format["min_size_bytes"] == 16_384
    assert nes_format["max_size_bytes"] == 4_194_304
    assert nes_format["pack_source"] == "builtin"


@pytest.mark.asyncio
async def test_platform_with_no_formats_still_appears(
    authed_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A Platform with zero PlatformFormat rows still surfaces
    (with an empty ``formats`` list) so the operator can see that
    bounds are not configured."""
    pid = await _seed_platform_with_formats(
        api_engine,
        name="Atari 2600",
        formats=[],
    )

    response = await authed_client.get("/api/v3/quality-definition")
    body = response.json()
    atari = next((r for r in body if r["platform_id"] == pid), None)
    assert atari is not None
    assert atari["formats"] == []


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/quality-definition")
    assert response.status_code == 401
