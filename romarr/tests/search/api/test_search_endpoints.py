"""Manual-search endpoint tests (T061)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.search.api.conftest import seed_admin_and_login


@pytest.mark.asyncio
async def test_manual_search_returns_round_report(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """No indexers configured → empty round but the response shape
    is the documented :class:`SearchRoundReport` JSON."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/rom/search/manual",
        json={"query": "Sonic the Hedgehog"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["search_type"] == "manual"
    assert body["candidates"] == []
    assert body["grabs"] == []
    assert body["correlation_id"]
    assert body["indexer_outcomes"] == {}


@pytest.mark.asyncio
async def test_manual_search_validates_payload(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Empty query is rejected by the Pydantic min_length=1 validator."""
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/rom/search/manual",
        json={"query": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_manual_search_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/rom/search/manual", json={"query": "Sonic"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_release_search_endpoint(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """T062 — POST /api/v3/rom/search/release/{id} runs a round
    scoped to the Release's bound Library profiles. With no indexers
    the response is an empty round but the shape matches
    :class:`SearchRoundReport`; the round_type is ``"manual"`` (the
    release-scoped round is a flavor of manual)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from romarr.domain.enums import DumpStatus, NamingConvention
    from romarr.domain.models import Game, Platform, Release
    from romarr.libraries.models import Library
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    await seed_admin_and_login(api_engine, api_client)

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        quality = QualityProfile(
            name="quality-rs",
            allowed_formats=["raw"],
            preferred_format="raw",
            require_dat_verified=False,
            upgrade_until_format="raw",
        )
        region = RegionProfile(
            name="region-rs",
            priorities=["USA"],
            allow_fallback_outside_priorities=True,
            exclude_regions=[],
        )
        dump = DumpProfile(
            name="dump-rs",
            allowed_dump_status=["verified"],
            allow_proto_beta=False,
            allow_hacks=False,
            allow_trainers=False,
            allow_translations=False,
        )
        language = LanguageProfile(
            name="lang-rs",
            required_languages=[],
            preferred_languages=["en"],
            exclude_japanese_only=False,
        )
        naming = NamingProfile(
            name="naming-rs",
            convention="no-intro",
            template="{{ game.title }}",
        )
        session.add_all([quality, region, dump, language, naming])
        await session.commit()
        for p in (quality, region, dump, language, naming):
            await session.refresh(p)

        library = Library(
            name="Cartridges",
            path="/tmp/lib-rs",
            quality_profile_id=quality.id,
            region_profile_id=region.id,
            dump_profile_id=dump.id,
            language_profile_id=language.id,
            naming_profile_id=naming.id,
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
            slug="sonic-rs",
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
            status="wanted",
            library_id=library.id,
        )
        session.add(release)
        await session.commit()
        await session.refresh(release)
        release_id = release.id

    response = await api_client.post(
        f"/api/v3/rom/search/release/{release_id}",
        json={"strict": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["search_type"] == "manual"
    assert body["candidates"] == []
    assert body["grabs"] == []
    assert body["indexer_outcomes"] == {}
    assert body["correlation_id"]


@pytest.mark.asyncio
async def test_release_search_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post("/api/v3/rom/search/release/1")
    assert response.status_code == 401
