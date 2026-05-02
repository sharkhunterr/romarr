"""Tests for the library + profile context loader (slice 80)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.importer._context import (
    LibraryContext,
    LibraryContextNotFound,
    load_library_context,
)
from romarr.libraries.models import Library
from romarr.profiles.models import (
    CustomFormat,
    DumpProfile,
    LanguageProfile,
    LibraryCustomFormat,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)


async def _seed_profiles(session: AsyncSession) -> dict[str, int]:
    """Insert one of every profile type, return their ids."""
    quality = QualityProfile(
        name="Default Quality",
        allowed_formats=["nes", "md", "smc"],
        preferred_format="md",
        upgrade_until_format="md",
    )
    region = RegionProfile(
        name="USA-first",
        priorities=["USA", "World"],
    )
    dump = DumpProfile(
        name="Verified only",
        allowed_dump_status=["verified", "good"],
    )
    language = LanguageProfile(
        name="English",
        required_languages=["en"],
        preferred_languages=["en"],
    )
    naming = NamingProfile(
        name="No-Intro",
        convention="no-intro",
        template="{{game.title}} ({{release.regions[0]}}).{{dump.format}}",
    )
    session.add_all([quality, region, dump, language, naming])
    await session.flush()
    return {
        "quality_id": quality.id,
        "region_id": region.id,
        "dump_id": dump.id,
        "language_id": language.id,
        "naming_id": naming.id,
    }


async def _seed_library(
    session: AsyncSession, profile_ids: dict[str, int]
) -> Library:
    library = Library(
        name="Mega Drive Lib",
        path="/library/megadrive",
        quality_profile_id=profile_ids["quality_id"],
        region_profile_id=profile_ids["region_id"],
        dump_profile_id=profile_ids["dump_id"],
        language_profile_id=profile_ids["language_id"],
        naming_profile_id=profile_ids["naming_id"],
    )
    session.add(library)
    await session.flush()
    return library


@pytest.mark.asyncio
async def test_load_library_context_returns_full_shape(
    async_session: AsyncSession,
) -> None:
    profile_ids = await _seed_profiles(async_session)
    library = await _seed_library(async_session, profile_ids)
    await async_session.commit()

    ctx = await load_library_context(
        session=async_session, library_id=library.id
    )
    assert isinstance(ctx, LibraryContext)
    assert ctx.library.id == library.id
    assert ctx.library.name == "Mega Drive Lib"
    assert ctx.quality.id == profile_ids["quality_id"]
    assert ctx.quality.name == "Default Quality"
    assert ctx.region.priorities == ["USA", "World"]
    assert ctx.dump.allowed_dump_status == ["verified", "good"]
    assert ctx.language.required_languages == ["en"]
    assert ctx.naming.convention == "no-intro"
    assert ctx.custom_formats == ()


@pytest.mark.asyncio
async def test_load_library_context_includes_custom_formats_sorted_by_score(
    async_session: AsyncSession,
) -> None:
    profile_ids = await _seed_profiles(async_session)
    library = await _seed_library(async_session, profile_ids)

    cf_high = CustomFormat(
        name="bonus", score=200, conditions=[{"type": "lang", "value": "en"}]
    )
    cf_low = CustomFormat(
        name="penalty", score=-50, conditions=[{"type": "lang", "value": "ja"}]
    )
    cf_mid = CustomFormat(
        name="meh", score=10, conditions=[{"type": "tag", "value": "rev1"}]
    )
    async_session.add_all([cf_high, cf_low, cf_mid])
    await async_session.flush()
    async_session.add_all([
        LibraryCustomFormat(
            library_id=library.id,
            custom_format_id=cf_high.id,
            created_at=datetime.now(UTC),
        ),
        LibraryCustomFormat(
            library_id=library.id,
            custom_format_id=cf_low.id,
            created_at=datetime.now(UTC),
        ),
        LibraryCustomFormat(
            library_id=library.id,
            custom_format_id=cf_mid.id,
            created_at=datetime.now(UTC),
        ),
    ])
    await async_session.commit()

    ctx = await load_library_context(
        session=async_session, library_id=library.id
    )
    assert len(ctx.custom_formats) == 3
    scores = [cf.score for cf in ctx.custom_formats]
    assert scores == [200, 10, -50]  # descending


@pytest.mark.asyncio
async def test_load_library_context_unknown_id_raises(
    async_session: AsyncSession,
) -> None:
    with pytest.raises(LibraryContextNotFound, match="library_id=99999"):
        await load_library_context(session=async_session, library_id=99999)


@pytest.mark.asyncio
async def test_library_context_is_frozen_dataclass(
    async_session: AsyncSession,
) -> None:
    """The dataclass is frozen so the orchestrator can't
    accidentally mutate the loaded profiles mid-pipeline."""
    profile_ids = await _seed_profiles(async_session)
    library = await _seed_library(async_session, profile_ids)
    await async_session.commit()

    ctx = await load_library_context(
        session=async_session, library_id=library.id
    )
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        ctx.quality = ctx.quality  # type: ignore[misc]
