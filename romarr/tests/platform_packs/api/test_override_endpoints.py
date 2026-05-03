"""Override + format-CRUD endpoint tests (T052, T053)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.domain.models import Platform
from tests.platform_packs.api.conftest import seed_admin_and_login


async def _seed_pack(
    api_client: httpx.AsyncClient,
    pack_yaml: Callable[[str], bytes],
) -> None:
    response = await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", pack_yaml("valid/two_platforms.yaml"), "text/yaml")},
    )
    assert response.status_code == 200


async def _resolve_id(api_engine: AsyncEngine, slug: str) -> int:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as s:
        plat = (
            await s.execute(select(Platform).where(Platform.slug == slug))
        ).scalar_one()
        return plat.id


# ---------------------------------------------------------------------------
# Override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_override_round_trip(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T052: POST → DELETE on /override flips and reverts pack_source."""
    await seed_admin_and_login(api_engine, api_client)
    await _seed_pack(api_client, pack_yaml)
    nes_id = await _resolve_id(api_engine, "nes")

    response = await api_client.post(f"/api/v3/rom/platform/{nes_id}/override")
    assert response.status_code == 200
    assert response.json()["pack_source"] == "user"

    response = await api_client.delete(f"/api/v3/rom/platform/{nes_id}/override")
    assert response.status_code == 200
    assert response.json()["pack_source"] == "community"


@pytest.mark.asyncio
async def test_override_unknown_platform_returns_404(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post("/api/v3/rom/platform/9999/override")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Format CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_list_does_not_require_override(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    await _seed_pack(api_client, pack_yaml)
    nes_id = await _resolve_id(api_engine, "nes")

    response = await api_client.get(f"/api/v3/rom/platform/{nes_id}/format")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 1
    assert all("extension" in r for r in rows)


@pytest.mark.asyncio
async def test_format_add_without_override_returns_409(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T053: format mutation against a non-overridden platform → HTTP 409."""
    await seed_admin_and_login(api_engine, api_client)
    await _seed_pack(api_client, pack_yaml)
    nes_id = await _resolve_id(api_engine, "nes")

    response = await api_client.post(
        f"/api/v3/rom/platform/{nes_id}/format",
        json={"extension": ".x", "format_type": "cartridge"},
    )
    assert response.status_code == 409
    assert response.json()["errorCode"] == "override_required"


@pytest.mark.asyncio
async def test_format_add_with_override_returns_201(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    await _seed_pack(api_client, pack_yaml)
    nes_id = await _resolve_id(api_engine, "nes")

    await api_client.post(f"/api/v3/rom/platform/{nes_id}/override")
    response = await api_client.post(
        f"/api/v3/rom/platform/{nes_id}/format",
        json={"extension": ".userx", "format_type": "cartridge"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["extension"] == ".userx"
    assert body["pack_source"] == "user"


@pytest.mark.asyncio
async def test_format_update_then_delete(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    await _seed_pack(api_client, pack_yaml)
    nes_id = await _resolve_id(api_engine, "nes")
    await api_client.post(f"/api/v3/rom/platform/{nes_id}/override")

    add = await api_client.post(
        f"/api/v3/rom/platform/{nes_id}/format",
        json={"extension": ".alpha", "format_type": "cartridge"},
    )
    fmt_id = add.json()["id"]

    upd = await api_client.put(
        f"/api/v3/rom/platform/{nes_id}/format/{fmt_id}",
        json={"max_size_bytes": 5_000_000},
    )
    assert upd.status_code == 200
    assert upd.json()["max_size_bytes"] == 5_000_000

    deleted = await api_client.delete(
        f"/api/v3/rom/platform/{nes_id}/format/{fmt_id}"
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_format_validation_rejects_bad_extension(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    await _seed_pack(api_client, pack_yaml)
    nes_id = await _resolve_id(api_engine, "nes")
    await api_client.post(f"/api/v3/rom/platform/{nes_id}/override")

    response = await api_client.post(
        f"/api/v3/rom/platform/{nes_id}/format",
        json={"extension": "no-leading-dot", "format_type": "cartridge"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_format_endpoints_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/rom/platform/1/format")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# slice 99 — GET /api/v3/rom/platform list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_platforms_returns_pack_contents_alphabetically(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """The two-platform pack ships NES + SNES. Both surface,
    sorted by `name` ascending."""
    await seed_admin_and_login(api_engine, api_client)
    await _seed_pack(api_client, pack_yaml)

    resp = await api_client.get("/api/v3/rom/platform")
    assert resp.status_code == 200
    body = resp.json()
    names = [row["name"] for row in body]
    assert names == sorted(names)
    assert any(row["slug"] == "nes" for row in body)
    assert any(row["slug"] == "snes" for row in body)


@pytest.mark.asyncio
async def test_list_platforms_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/rom/platform")
    assert resp.status_code == 401
