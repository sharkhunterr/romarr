"""ESDE per-import dispatch (spec 009 T059 / FR-018).

When the picked Library has ``exporter_esde_enabled=True``, a
successful auto-import re-emits ``gamelist.xml`` in
``<library>/<platform_slug>/``. When the flag is False, no
file is written.

The full "materialise every Game on the platform" renderer
fan-out ships with the per-import dispatch + spec 002
metadata aggregator integration. This slice's contract is
the gate semantics — the file exists when enabled, doesn't
when disabled.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, Release
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.libraries.models import Library


async def _seed_chain(
    session: AsyncSession,
    library_root: Path,
    *,
    exporter_esde_enabled: bool,
) -> tuple[Library, Game, Release]:
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    quality = QualityProfile(
        name="quality-esde",
        allowed_formats=["raw"],
        preferred_format="raw",
        require_dat_verified=False,
        upgrade_until_format="raw",
    )
    region = RegionProfile(
        name="region-esde",
        priorities=["USA"],
        allow_fallback_outside_priorities=True,
        exclude_regions=[],
    )
    dump = DumpProfile(
        name="dump-esde",
        allowed_dump_status=["verified"],
        allow_proto_beta=False,
        allow_hacks=False,
        allow_trainers=False,
        allow_translations=False,
    )
    language = LanguageProfile(
        name="language-esde",
        required_languages=[],
        preferred_languages=["en"],
        exclude_japanese_only=False,
    )
    naming = NamingProfile(
        name="naming-esde",
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
        exporter_esde_enabled=exporter_esde_enabled,
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
        slug="sonic-esde",
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
async def test_disabled_emits_nothing(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """T059 — exporter_esde_enabled=False → no gamelist.xml."""
    library_root = tmp_path / "library"
    library_root.mkdir()
    _, _, _ = await _seed_chain(
        async_session, library_root, exporter_esde_enabled=False
    )

    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    _write_megadrive_rom(rom)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True

    # gamelist.xml should NOT exist — flag disabled.
    gamelist = library_root / "megadrive" / "gamelist.xml"
    assert not gamelist.exists()


@pytest.mark.asyncio
async def test_enabled_emits_gamelist_xml(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """exporter_esde_enabled=True → gamelist.xml lands in the
    per-platform subfolder."""
    library_root = tmp_path / "library"
    library_root.mkdir()
    _, _, _ = await _seed_chain(
        async_session, library_root, exporter_esde_enabled=True
    )

    rom = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    _write_megadrive_rom(rom)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is True

    gamelist = library_root / "megadrive" / "gamelist.xml"
    assert gamelist.exists()
    body = gamelist.read_text()
    assert "Sonic the Hedgehog" in body
