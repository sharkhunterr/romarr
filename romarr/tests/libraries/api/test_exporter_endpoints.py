"""Exporter catalog endpoint tests (slice 279 / spec 009 T082).

Covers the read-only surface shipped today:
  * GET /api/v3/rom/exporters         → list
  * GET /api/v3/rom/exporters/{name}  → one
  * GET /api/v3/rom/exporters/unknown → 404

Per-import dispatch + ``POST /run`` are deferred to a future
slice when the spec 008 importer's per-import fan-out arrives.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

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


@pytest.mark.asyncio
async def test_lists_the_four_documented_exporters(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/rom/exporters")
    assert response.status_code == 200
    body = response.json()
    names = {row["name"] for row in body}
    assert names == {"esde", "pegasus", "launchbox", "romm"}


@pytest.mark.asyncio
async def test_each_row_carries_format_metadata(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/rom/exporters")
    by_name = {row["name"]: row for row in response.json()}
    assert by_name["esde"]["format"] == "xml"
    assert by_name["pegasus"]["format"] == "txt"
    assert by_name["launchbox"]["format"] == "xml"
    assert by_name["romm"]["format"] == "http"
    for row in by_name.values():
        assert row["available"] is True
        assert isinstance(row["description"], str)
        assert len(row["description"]) > 0


@pytest.mark.asyncio
async def test_read_one_exporter_by_name(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/rom/exporters/esde")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "esde"
    assert body["format"] == "xml"


@pytest.mark.asyncio
async def test_unknown_name_returns_404(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v3/rom/exporters/not-a-real-one")
    assert response.status_code == 404
    # Spec-013 envelope unwraps to the top level via the app's
    # error handler; the route raises with a dict detail.
    assert response.json()["errorCode"] == "exporter_not_found"


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v3/rom/exporters")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# T078 — POST /exporters/{name}/run
# ---------------------------------------------------------------------------


async def _seed_library_with_imported_game(
    api_engine: AsyncEngine, tmp_path_root: str, *, esde_enabled: bool = True
) -> tuple[int, str]:
    """Seed a Library + Platform + Game + Release + Dump and return
    (library_id, platform_slug) so the run endpoint has data to
    materialize."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from romarr.domain.enums import DumpStatus, NamingConvention
    from romarr.domain.models import Dump, Game, Platform, Release
    from romarr.libraries.models import Library
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        quality = QualityProfile(
            name="quality-run",
            allowed_formats=["raw"],
            preferred_format="raw",
            require_dat_verified=False,
            upgrade_until_format="raw",
        )
        region = RegionProfile(
            name="region-run",
            priorities=["USA"],
            allow_fallback_outside_priorities=True,
            exclude_regions=[],
        )
        dump = DumpProfile(
            name="dump-run",
            allowed_dump_status=["verified"],
            allow_proto_beta=False,
            allow_hacks=False,
            allow_trainers=False,
            allow_translations=False,
        )
        language = LanguageProfile(
            name="lang-run",
            required_languages=[],
            preferred_languages=["en"],
            exclude_japanese_only=False,
        )
        naming = NamingProfile(
            name="naming-run",
            convention="no-intro",
            template="{{ game.title }}",
        )
        session.add_all([quality, region, dump, language, naming])
        await session.commit()
        for p in (quality, region, dump, language, naming):
            await session.refresh(p)

        library = Library(
            name="Cartridges-run",
            path=tmp_path_root,
            quality_profile_id=quality.id,
            region_profile_id=region.id,
            dump_profile_id=dump.id,
            language_profile_id=language.id,
            naming_profile_id=naming.id,
            exporter_esde_enabled=esde_enabled,
        )
        session.add(library)
        await session.commit()
        await session.refresh(library)

        platform = Platform(slug="megadrive", name="Mega Drive")
        session.add(platform)
        await session.commit()
        await session.refresh(platform)

        game = Game(
            platform_id=platform.id,
            slug="sonic-run",
            title="Sonic the Hedgehog",
            monitored=True,
        )
        session.add(game)
        await session.commit()
        await session.refresh(game)

        release = Release(
            game_id=game.id,
            name="Sonic the Hedgehog (USA)",
            regions=["USA"],
            languages=["en"],
            dump_status=DumpStatus.VERIFIED,
            naming_convention=NamingConvention.NO_INTRO,
            status="imported",
            library_id=library.id,
        )
        session.add(release)
        await session.commit()
        await session.refresh(release)

        from pathlib import Path as _P

        rom_path = _P(tmp_path_root) / "megadrive" / "Sonic the Hedgehog (USA).md"
        rom_path.parent.mkdir(parents=True, exist_ok=True)
        rom_path.write_bytes(b"\x00" * 16)

        d = Dump(
            release_id=release.id,
            path=str(rom_path),
            original_filename=rom_path.name,
            size_bytes=16,
            sha1="0" * 40,
            crc32="00000000",
            md5="0" * 32,
            format="raw",
        )
        session.add(d)
        await session.commit()

        return library.id, platform.slug


@pytest.mark.asyncio
async def test_run_esde_writes_gamelist_xml(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path,
) -> None:
    library_id, platform_slug = await _seed_library_with_imported_game(
        api_engine, str(tmp_path)
    )
    response = await authed_client.post(
        "/api/v3/rom/exporters/esde/run",
        json={"library_id": library_id, "platform_slug": platform_slug},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "esde"
    assert body["games_written"] == 1
    assert body["written"] is True

    gamelist = tmp_path / "megadrive" / "gamelist.xml"
    assert gamelist.exists()
    content = gamelist.read_text()
    assert "Sonic the Hedgehog" in content


@pytest.mark.asyncio
async def test_run_esde_disabled_returns_409(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path,
) -> None:
    library_id, platform_slug = await _seed_library_with_imported_game(
        api_engine, str(tmp_path), esde_enabled=False
    )
    response = await authed_client.post(
        "/api/v3/rom/exporters/esde/run",
        json={"library_id": library_id, "platform_slug": platform_slug},
    )
    assert response.status_code == 409
    assert response.json()["errorCode"] == "exporter_disabled_on_library"


@pytest.mark.asyncio
async def test_run_unwired_exporter_returns_501(
    authed_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path,
) -> None:
    library_id, platform_slug = await _seed_library_with_imported_game(
        api_engine, str(tmp_path)
    )
    response = await authed_client.post(
        "/api/v3/rom/exporters/pegasus/run",
        json={"library_id": library_id, "platform_slug": platform_slug},
    )
    assert response.status_code == 501
    assert response.json()["errorCode"] == "exporter_run_not_wired"


@pytest.mark.asyncio
async def test_run_unknown_exporter_returns_404(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.post(
        "/api/v3/rom/exporters/not-a-real-one/run",
        json={"library_id": 1, "platform_slug": "megadrive"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_run_missing_library_returns_404(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.post(
        "/api/v3/rom/exporters/esde/run",
        json={"library_id": 99999, "platform_slug": "megadrive"},
    )
    assert response.status_code == 404
    assert response.json()["errorCode"] == "library_not_found"
