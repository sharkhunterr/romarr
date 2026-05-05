"""Orchestrator MOVE step + destination-collision parking
(spec 008 CL003 / CL008 + FR-007).

When the picked Release is bound to a Library whose path
exists on disk, the orchestrator moves the source file into
``<library.path>/<platform.slug>/<filename>`` (hardlink-first)
before persisting the Dump.

Destination collisions (a different SHA-1 already at dest, no
``force=true``) → park with ``destination_collision``
rejection reason and auto-blocklist via the spec 007
helper (CL003).
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release, UnidentifiedDump
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.libraries.models import Library
from romarr.search.models import Blocklist


async def _seed_chain(
    session: AsyncSession, library_root: Path
) -> tuple[Library, Game, Release]:
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    quality = QualityProfile(
        name="quality-mv",
        allowed_formats=["raw"],
        preferred_format="raw",
        require_dat_verified=False,
        upgrade_until_format="raw",
    )
    region = RegionProfile(
        name="region-mv",
        priorities=["USA"],
        allow_fallback_outside_priorities=True,
        exclude_regions=[],
    )
    dump = DumpProfile(
        name="dump-mv",
        allowed_dump_status=["verified"],
        allow_proto_beta=False,
        allow_hacks=False,
        allow_trainers=False,
        allow_translations=False,
    )
    language = LanguageProfile(
        name="language-mv",
        required_languages=[],
        preferred_languages=["en"],
        exclude_japanese_only=False,
    )
    naming = NamingProfile(
        name="naming-mv",
        convention="no-intro",
        template="{{ game.title }}",
    )
    session.add_all([quality, region, dump, language, naming])
    await session.commit()
    for p in (quality, region, dump, language, naming):
        await session.refresh(p)

    library = Library(
        name="Cartridges",
        path=str(library_root),
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
        slug="sonic-mv",
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


def _write_megadrive_rom(path: Path) -> None:
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(body))


@pytest.mark.asyncio
async def test_auto_import_moves_into_library_tree(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Library.path exists on disk → source file is hardlinked
    into ``<library>/<platform_slug>/<filename>``."""
    library_root = tmp_path / "library"
    library_root.mkdir()
    _, _, release = await _seed_chain(async_session, library_root)

    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    _write_megadrive_rom(rom)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True

    expected_dest = library_root / "megadrive" / rom.name
    assert expected_dest.exists()

    dump = (
        await async_session.execute(
            select(Dump).where(Dump.release_id == release.id)
        )
    ).scalar_one()
    assert dump.path == str(expected_dest)


@pytest.mark.asyncio
async def test_destination_collision_parks_with_typed_reason(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """A different file already at the destination → park with
    ``destination_collision`` rejection reason + auto-blocklist
    fires (CL003 + CL001)."""
    library_root = tmp_path / "library"
    library_root.mkdir()
    _, _, _ = await _seed_chain(async_session, library_root)

    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    _write_megadrive_rom(rom)

    # Plant a different file at the destination (different bytes
    # → different SHA-1).
    dest = library_root / "megadrive" / rom.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\xff" * 4096)  # different content

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is False

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    assert parked.rejection_reason == "destination_collision"

    # CL001 — destination_collision is in
    # _BLOCKLIST_WORTHY_REASONS so a Blocklist row landed too.
    blocklist = (
        await async_session.execute(select(Blocklist))
    ).scalars().all()
    assert len(blocklist) == 1
    assert blocklist[0].reason == "destination_collision"
    assert blocklist[0].added_by == "system"


@pytest.mark.asyncio
async def test_auto_import_in_place_when_library_path_missing(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When Library.path doesn't exist on disk (pre-deployment
    / test fixture), the orchestrator falls back to the
    in-place path — Dump.path = source_path."""
    # Library.path points at a non-existent directory.
    nonexistent_root = tmp_path / "does-not-exist"
    _, _, release = await _seed_chain(async_session, nonexistent_root)

    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    _write_megadrive_rom(rom)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True

    dump = (
        await async_session.execute(
            select(Dump).where(Dump.release_id == release.id)
        )
    ).scalar_one()
    # In-place — Dump.path points at source.
    assert dump.path == str(rom)
