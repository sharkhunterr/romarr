"""Orchestrator preserve_archive lifecycle (spec 008 T030 / FR-005).

After a successful auto-import from an archive source, the
orchestrator deletes the archive iff the owning Library's
``preserve_archive`` flag is False. ``preserve_archive=True``
keeps the archive on disk so the operator can re-import.

The check walks Release.library_id → Library.preserve_archive;
when the Release has no library binding the archive is kept by
default (operator intent unknown).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, Release
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.libraries.models import Library


async def _seed_library_chain(
    session: AsyncSession, *, preserve_archive: bool
) -> tuple[Library, Game, Release]:
    """Seed the full Library + Game + wanted Release with the
    matching profile FKs."""
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    quality = QualityProfile(
        name="quality-pa",
        allowed_formats=["raw"],
        preferred_format="raw",
        require_dat_verified=False,
        upgrade_until_format="raw",
    )
    region = RegionProfile(
        name="region-pa",
        priorities=["USA"],
        allow_fallback_outside_priorities=True,
        exclude_regions=[],
    )
    dump = DumpProfile(
        name="dump-pa",
        allowed_dump_status=["verified"],
        allow_proto_beta=False,
        allow_hacks=False,
        allow_trainers=False,
        allow_translations=False,
    )
    language = LanguageProfile(
        name="language-pa",
        required_languages=[],
        preferred_languages=["en"],
        exclude_japanese_only=False,
    )
    naming = NamingProfile(
        name="naming-pa",
        convention="no-intro",
        template="{{ game.title }}",
    )
    session.add_all([quality, region, dump, language, naming])
    await session.commit()
    for p in (quality, region, dump, language, naming):
        await session.refresh(p)

    library = Library(
        name="Cartridges",
        path="/srv/roms/cart",
        quality_profile_id=quality.id,
        region_profile_id=region.id,
        dump_profile_id=dump.id,
        language_profile_id=language.id,
        naming_profile_id=naming.id,
        preserve_archive=preserve_archive,
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
        slug="sonic-pa",
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


def _write_megadrive_zip(tmp_path: Path) -> tuple[Path, str]:
    """Build a valid .zip wrapping a recognizable Mega Drive ROM
    + return (archive_path, rom_basename)."""
    archive = tmp_path / "downloads" / "Sonic.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom_name = "Sonic the Hedgehog (USA).bin"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(rom_name, bytes(body))
    return archive, rom_name


@pytest.mark.asyncio
async def test_archive_deleted_when_preserve_archive_false(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """preserve_archive=False → archive is unlinked after the
    successful in-place auto-import."""
    _, _, _ = await _seed_library_chain(
        async_session, preserve_archive=False
    )

    archive, _ = _write_megadrive_zip(tmp_path)
    assert archive.exists()

    context = ImportContext(
        source_path=archive,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True
    # Archive removed.
    assert not archive.exists()


@pytest.mark.asyncio
async def test_archive_kept_when_preserve_archive_true(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """preserve_archive=True → archive stays on disk."""
    _, _, _ = await _seed_library_chain(
        async_session, preserve_archive=True
    )

    archive, _ = _write_megadrive_zip(tmp_path)
    assert archive.exists()

    context = ImportContext(
        source_path=archive,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True
    assert archive.exists()


@pytest.mark.asyncio
async def test_archive_kept_when_release_has_no_library(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When Release.library_id is NULL the orchestrator preserves
    the archive (operator intent unknown)."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-no-lib",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    release = Release(
        game_id=game.id,
        name="Sonic the Hedgehog (USA)",
        regions=["USA"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        status="wanted",
        library_id=None,  # orphan
    )
    async_session.add(release)
    await async_session.commit()
    await async_session.refresh(release)

    archive, _ = _write_megadrive_zip(tmp_path)
    assert archive.exists()

    context = ImportContext(
        source_path=archive,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True
    # Library binding unknown → archive preserved.
    assert archive.exists()
