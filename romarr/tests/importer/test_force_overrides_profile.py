"""Force-overrides-profile manual flow (spec 008 T084 / FR-021 / US4.2).

When ``ImportContext.force=True``, a profile-gate REJECT
becomes a warning rather than a halt — the orchestrator still
auto-imports the file but stamps the rejection reason on the
audit row's ``warning`` column.

The complementary case (``force=False``, profile rejects) →
the import fails, file lands in unidentified_dump with the
structured ``profile:*`` rejection reason.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, Release, UnidentifiedDump
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.libraries.models import Library


async def _seed_library_with_excluding_region(
    session: AsyncSession,
) -> tuple[Library, Game, Release]:
    """Seed a Library whose Region profile excludes USA. The
    Release region is USA → profile-gate REJECTs."""
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    quality = QualityProfile(
        name="quality-force",
        allowed_formats=["raw"],
        preferred_format="raw",
        require_dat_verified=False,
        upgrade_until_format="raw",
    )
    region = RegionProfile(
        name="region-force-eu",
        priorities=["EUR"],
        allow_fallback_outside_priorities=False,
        exclude_regions=["USA"],  # USA explicitly excluded
    )
    dump = DumpProfile(
        name="dump-force",
        allowed_dump_status=["verified"],
        allow_proto_beta=False,
        allow_hacks=False,
        allow_trainers=False,
        allow_translations=False,
    )
    language = LanguageProfile(
        name="language-force",
        required_languages=[],
        preferred_languages=["en"],
        exclude_japanese_only=False,
    )
    naming = NamingProfile(
        name="naming-force",
        convention="no-intro",
        template="{{ game.title }}",
    )
    session.add_all([quality, region, dump, language, naming])
    await session.commit()
    for p in (quality, region, dump, language, naming):
        await session.refresh(p)

    library = Library(
        name="EU-only",
        path="/srv/roms/eu",
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
        slug="sonic-force",
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

    return library, game, release


def _write_megadrive_rom(tmp_path: Path) -> Path:
    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom.write_bytes(bytes(body))
    return rom


@pytest.mark.asyncio
async def test_profile_reject_without_force_lands_in_unidentified(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """``force=False`` (the default) + profile REJECT → import
    fails, file is parked with ``profile:region`` rejection."""
    _, _, _ = await _seed_library_with_excluding_region(async_session)
    rom = _write_megadrive_rom(tmp_path)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
        # force defaults to False
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is False

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    assert parked.rejection_reason == "profile:region"


@pytest.mark.asyncio
async def test_force_true_overrides_profile_reject(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """T084 — ``force=True`` + profile REJECT → import succeeds;
    the rejection reason carries forward as a warning. (The
    spec 008 manual_import_known doesn't yet expose a warning
    field on the outcome — slice 318 commits to gating the
    profile-rejection-as-warning behavior at the orchestrator
    level: force=True bypasses the hard-reject branch and the
    auto-import lands.)"""
    _, _, release = await _seed_library_with_excluding_region(async_session)
    rom = _write_megadrive_rom(tmp_path)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
        force=True,
    )
    outcome = await run_import(context, session=async_session)
    # force=True → import lands.
    assert outcome.success is True
    assert outcome.release_id == release.id

    # Release flipped to imported.
    refreshed = (
        await async_session.execute(
            select(Release).where(Release.id == release.id)
        )
    ).scalar_one()
    assert refreshed.status == "imported"

    # No parking happened.
    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one_or_none()
    assert parked is None
