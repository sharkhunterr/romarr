"""Orchestrator ``delete_after_import`` lifecycle.

The library schema's ``delete_after_import`` flag was wired through
the API + DB but no code ever consulted it — Romarr's downloads
folder accumulated GB of orphan source files after every successful
import (one of our installs hit 9.5 GB of Minerva downloads + 29 GB
of leaked rom_pack extracts). This module pins the new behaviour:

  * ``delete_after_import=True`` → source file AND its ``.extracted``
    companion dir are removed after a clean import.
  * ``delete_after_import=False`` → source is preserved (today's
    default; matches the historical "copy and keep" intent).
  * Source path inside the library destination is never touched
    (would otherwise unlink the imported file).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, Release
from romarr.importer.orchestrator import _maybe_delete_source_post_import
from romarr.libraries.models import Library


async def _seed(
    session: AsyncSession,
    *,
    delete_after_import: bool,
    library_path: str,
) -> Release:
    """Minimal Library + Game + Release chain so the helper has
    something to walk. We don't need the profile FKs here — the
    helper only reads release.library_id → library.delete_after_import."""
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    suffix = uuid4().hex[:8]
    quality = QualityProfile(
        name=f"quality-{suffix}",
        allowed_formats=["raw"],
        preferred_format="raw",
        require_dat_verified=False,
        upgrade_until_format="raw",
    )
    region = RegionProfile(
        name=f"region-{suffix}",
        priorities=["USA"],
        allow_fallback_outside_priorities=True,
        exclude_regions=[],
    )
    dump = DumpProfile(
        name=f"dump-{suffix}",
        allowed_dump_status=["verified"],
        allow_proto_beta=False,
        allow_hacks=False,
        allow_trainers=False,
        allow_translations=False,
    )
    language = LanguageProfile(
        name=f"language-{suffix}",
        required_languages=[],
        preferred_languages=["en"],
        exclude_japanese_only=False,
    )
    naming = NamingProfile(
        name=f"naming-{suffix}",
        convention="no-intro",
        template="{{ game.title }}",
    )
    session.add_all([quality, region, dump, language, naming])
    await session.commit()
    for p in (quality, region, dump, language, naming):
        await session.refresh(p)

    library = Library(
        name=f"ROMs-{suffix}",
        path=library_path,
        quality_profile_id=quality.id,
        region_profile_id=region.id,
        dump_profile_id=dump.id,
        language_profile_id=language.id,
        naming_profile_id=naming.id,
        delete_after_import=delete_after_import,
    )
    session.add(library)
    platform = Platform(slug=f"plat-{suffix}", name="P")
    session.add(platform)
    await session.commit()
    await session.refresh(library)
    await session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug=f"g-{uuid4().hex[:8]}",
        title="Game",
        monitored=True,
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)

    release = Release(
        game_id=game.id,
        name="Release",
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
    return release


@pytest.mark.asyncio
async def test_source_deleted_when_flag_true(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    release = await _seed(
        async_session, delete_after_import=True, library_path=str(tmp_path / "lib")
    )
    src = tmp_path / "downloads" / "game.iso"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"x" * 16)
    assert src.exists()

    await _maybe_delete_source_post_import(
        session=async_session,
        release_id=release.id,
        original_source=src,
    )

    assert not src.exists()


@pytest.mark.asyncio
async def test_source_kept_when_flag_false(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    release = await _seed(
        async_session,
        delete_after_import=False,
        library_path=str(tmp_path / "lib"),
    )
    src = tmp_path / "downloads" / "game.iso"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"x" * 16)

    await _maybe_delete_source_post_import(
        session=async_session,
        release_id=release.id,
        original_source=src,
    )

    assert src.exists()


@pytest.mark.asyncio
async def test_extracted_sibling_purged_alongside_archive(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Grabarr / the importer drop a ``<file>.extracted/`` dir next
    to a downloaded archive while unpacking — that dir is just as
    orphan as the archive once the bytes landed in the library."""
    release = await _seed(
        async_session, delete_after_import=True, library_path=str(tmp_path / "lib")
    )
    archive = tmp_path / "downloads" / "Game.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"zip-bytes")
    extracted = tmp_path / "downloads" / "Game.zip.extracted"
    extracted.mkdir()
    (extracted / "game.iso").write_bytes(b"y" * 16)

    await _maybe_delete_source_post_import(
        session=async_session,
        release_id=release.id,
        original_source=archive,
    )

    assert not archive.exists()
    assert not extracted.exists()


@pytest.mark.asyncio
async def test_source_inside_library_is_not_touched(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When the source path lives under the library destination
    (move_and_remove already put it there), the helper bails out —
    deleting would nuke the imported copy itself."""
    lib_root = tmp_path / "lib"
    lib_root.mkdir()
    release = await _seed(
        async_session, delete_after_import=True, library_path=str(lib_root)
    )
    src = lib_root / "gba" / "game.gba"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"x" * 32)

    await _maybe_delete_source_post_import(
        session=async_session,
        release_id=release.id,
        original_source=src,
    )

    assert src.exists(), "library-resident source must be preserved"


@pytest.mark.asyncio
async def test_release_without_library_is_noop(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Release.library_id IS NULL → operator intent unknown, source
    stays on disk."""
    platform = Platform(slug=f"plat-{uuid4().hex[:8]}", name="P")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)
    game = Game(
        platform_id=platform.id,
        slug=f"orphan-{uuid4().hex[:8]}",
        title="Orphan",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)
    release = Release(
        game_id=game.id,
        name="Orphan",
        regions=["USA"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        status="imported",
        library_id=None,
    )
    async_session.add(release)
    await async_session.commit()
    await async_session.refresh(release)

    src = tmp_path / "g.iso"
    src.write_bytes(b"x")

    await _maybe_delete_source_post_import(
        session=async_session,
        release_id=release.id,
        original_source=src,
    )

    assert src.exists()
