"""Library backfill + orphan-releases health tests (spec 009 CL008)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release
from romarr.libraries._orphan_health import check_orphan_releases_on_startup
from romarr.libraries.models import Library
from romarr.notifications.channel import EventChannel
from romarr.notifications.types import EventType, OnHealthIssuePayload


@pytest.fixture
async def seeded_release_with_library_dump(
    async_session: AsyncSession,
) -> tuple[Library, Release]:
    """Library + Game + Release + Dump where the Dump path is
    INSIDE the library path. Backfill should bind the Release to
    the Library."""
    profile_ids = await _seed_minimal_profiles(async_session)
    library = Library(
        name="Cartridges",
        path="/srv/roms/cartridges",
        quality_profile_id=profile_ids["quality"],
        region_profile_id=profile_ids["region"],
        dump_profile_id=profile_ids["dump"],
        language_profile_id=profile_ids["language"],
        naming_profile_id=profile_ids["naming"],
    )
    async_session.add(library)
    await async_session.commit()
    await async_session.refresh(library)

    platform = Platform(slug="megadrive-bf", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()

    game = Game(platform_id=platform.id, slug="sonic-bf", title="Sonic")
    async_session.add(game)
    await async_session.commit()

    release = Release(
        game_id=game.id,
        name="Sonic (USA)",
        regions=["USA"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        library_id=None,  # orphan until backfill
        status="imported",
    )
    async_session.add(release)
    await async_session.commit()
    await async_session.refresh(release)

    dump = Dump(
        release_id=release.id,
        path="/srv/roms/cartridges/Sonic the Hedgehog (USA).md",
        original_filename="Sonic the Hedgehog (USA).md",
        size_bytes=4096,
        format="raw",
        sha1="0" * 40,
        crc32="abcdef01",
        md5="0" * 32,
    )
    async_session.add(dump)
    await async_session.commit()

    return library, release


async def _seed_minimal_profiles(session: AsyncSession) -> dict[str, int]:
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    quality = QualityProfile(
        name="quality-bf",
        allowed_formats=["raw"],
        preferred_format="raw",
        require_dat_verified=False,
        upgrade_until_format="raw",
    )
    region = RegionProfile(
        name="region-bf",
        priorities=["USA"],
        allow_fallback_outside_priorities=True,
        exclude_regions=[],
    )
    dump = DumpProfile(
        name="dump-bf",
        allowed_dump_status=["verified"],
        allow_proto_beta=False,
        allow_hacks=False,
        allow_trainers=False,
        allow_translations=False,
    )
    language = LanguageProfile(
        name="language-bf",
        required_languages=[],
        preferred_languages=["en"],
        exclude_japanese_only=False,
    )
    naming = NamingProfile(
        name="naming-bf",
        convention="no-intro",
        template="{{ game.title }}",
    )
    session.add_all([quality, region, dump, language, naming])
    await session.commit()
    await session.refresh(quality)
    await session.refresh(region)
    await session.refresh(dump)
    await session.refresh(language)
    await session.refresh(naming)
    return {
        "quality": quality.id,
        "region": region.id,
        "dump": dump.id,
        "language": language.id,
        "naming": naming.id,
    }


@pytest.mark.asyncio
async def test_orphan_releases_health_emits_when_orphans_exist(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
    seeded_release_with_library_dump: tuple[Library, Release],
) -> None:
    """CL003 — when ≥ 1 Release has library_id IS NULL, the
    startup check emits one OnHealthIssue with the count."""
    # Seed leaves library_id NULL on the Release (orphan).
    library, release = seeded_release_with_library_dump
    assert release.library_id is None

    received: list[OnHealthIssuePayload] = []

    async def _capture(event):  # type: ignore[no-untyped-def]
        if event.event_type == EventType.ON_HEALTH_ISSUE:
            received.append(event)

    channel = EventChannel()
    await channel.start()
    channel.subscribe_global(_capture)

    try:
        count = await check_orphan_releases_on_startup(
            sessionmaker=async_sessionmaker_factory,
            event_channel=channel,
        )
        # Channel publishes are async; wait for the queue to drain.
        await channel.drain()
    finally:
        channel.unsubscribe_global(_capture)
        await channel.stop()

    assert count >= 1
    assert len(received) == 1
    event = received[0]
    assert event.component == "orphan-releases"
    assert event.severity == "warning"
    assert "won't be scanned" in event.message


@pytest.mark.asyncio
async def test_orphan_releases_health_silent_when_clean(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
) -> None:
    """No orphans → no event published."""
    received: list[OnHealthIssuePayload] = []

    async def _capture(event):  # type: ignore[no-untyped-def]
        received.append(event)

    channel = EventChannel()
    await channel.start()
    channel.subscribe_global(_capture)

    try:
        count = await check_orphan_releases_on_startup(
            sessionmaker=async_sessionmaker_factory,
            event_channel=channel,
        )
        await channel.drain()
    finally:
        channel.unsubscribe_global(_capture)
        await channel.stop()

    assert count == 0
    assert received == []
