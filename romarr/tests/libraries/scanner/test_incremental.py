"""Incremental-scanner direct-handler tests (spec 009 T044, T045).

These tests drive the scanner's domain-level handlers directly
rather than going through watchdog's observer thread — that
keeps them deterministic + fast. The watchdog→handler dispatch
is exercised separately by ``test_incremental_polling.py`` (T046)
and the inotify integration test (T043).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release
from romarr.libraries.models import Library
from romarr.libraries.scanner.incremental import IncrementalScanner

from tests.libraries.scanner.test_full_scan import (
    _seed_minimal_profiles,
)


@pytest.fixture
async def seeded_library_and_release(
    async_session: AsyncSession, tmp_path: Path
) -> tuple[Library, Release, Path]:
    """Library + one Game/Release + a real on-disk file the Dump
    can point at."""
    library_root = tmp_path / "library"
    library_root.mkdir()

    rom_path = library_root / "Sonic the Hedgehog (USA).md"
    rom_path.write_bytes(b"\x00" * 4096)

    profile_ids = await _seed_minimal_profiles(async_session)
    library = Library(
        name="Cartridges",
        path=str(library_root),
        quality_profile_id=profile_ids["quality"],
        region_profile_id=profile_ids["region"],
        dump_profile_id=profile_ids["dump"],
        language_profile_id=profile_ids["language"],
        naming_profile_id=profile_ids["naming"],
    )
    async_session.add(library)
    await async_session.commit()
    await async_session.refresh(library)

    platform = Platform(name="Mega Drive", slug="megadrive-sonic-inc")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(platform_id=platform.id, slug="sonic-inc", title="Sonic")
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    release = Release(
        game_id=game.id,
        name="Sonic (USA)",
        regions=["USA"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        library_id=library.id,
        status="imported",
    )
    async_session.add(release)
    await async_session.commit()
    await async_session.refresh(release)

    dump = Dump(
        release_id=release.id,
        path=str(rom_path),
        original_filename=rom_path.name,
        size_bytes=4096,
        format="raw",
        sha1="0" * 40,
        crc32="abcdef01",
        md5="0" * 32,
    )
    async_session.add(dump)
    await async_session.commit()

    return library, release, rom_path


@pytest.mark.asyncio
async def test_rename_updates_path_no_rehash(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
    seeded_library_and_release: tuple[Library, Release, Path],
) -> None:
    """T044 — rename inside the library updates ``Dump.path``."""
    library, _release, rom_path = seeded_library_and_release
    new_path = rom_path.parent / "Sonic the Hedgehog (USA) - renamed.md"
    rom_path.rename(new_path)

    scanner = IncrementalScanner(
        sessionmaker=async_sessionmaker_factory,
        library_id=library.id,
        library_path=Path(library.path),
        accepted_extensions={".md"},
    )

    await scanner.handle_moved(rom_path, new_path)

    refreshed = (
        await async_session.execute(select(Dump).where(Dump.path == str(new_path)))
    ).scalar_one_or_none()
    assert refreshed is not None
    assert scanner.counters.renamed == 1


@pytest.mark.asyncio
async def test_rename_outside_library_orphans(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
    seeded_library_and_release: tuple[Library, Release, Path],
    tmp_path: Path,
) -> None:
    """T045 — moving a file outside the library orphans the Dump
    + transitions the Release to ``status='wanted'``."""
    library, release, rom_path = seeded_library_and_release
    elsewhere = tmp_path / "elsewhere" / rom_path.name
    elsewhere.parent.mkdir(parents=True, exist_ok=True)
    rom_path.rename(elsewhere)

    scanner = IncrementalScanner(
        sessionmaker=async_sessionmaker_factory,
        library_id=library.id,
        library_path=Path(library.path),
        accepted_extensions={".md"},
    )

    release_id = release.id
    await async_session.close()
    await scanner.handle_moved(rom_path, elsewhere)

    async with async_sessionmaker_factory() as fresh:
        refreshed_dump = (
            await fresh.execute(
                select(Dump).where(Dump.release_id == release_id)
            )
        ).scalar_one_or_none()
        assert refreshed_dump is None  # orphaned + deleted

        refreshed_release = (
            await fresh.execute(
                select(Release).where(Release.id == release_id)
            )
        ).scalar_one()
        assert refreshed_release.status == "wanted"
    assert scanner.counters.deleted == 1


@pytest.mark.asyncio
async def test_delete_orphans_dump(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
    seeded_library_and_release: tuple[Library, Release, Path],
) -> None:
    """Bonus — deleted-event mirrors moved-out: Release flips
    to wanted (FR-011)."""
    library, release, rom_path = seeded_library_and_release

    scanner = IncrementalScanner(
        sessionmaker=async_sessionmaker_factory,
        library_id=library.id,
        library_path=Path(library.path),
        accepted_extensions={".md"},
    )

    release_id = release.id
    await async_session.close()
    await scanner.handle_deleted(rom_path)

    async with async_sessionmaker_factory() as fresh:
        refreshed_release = (
            await fresh.execute(
                select(Release).where(Release.id == release_id)
            )
        ).scalar_one()
        assert refreshed_release.status == "wanted"
    assert scanner.counters.deleted == 1


@pytest.mark.asyncio
async def test_handle_created_links_existing_dump_by_sha1(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker,
    seeded_library_and_release: tuple[Library, Release, Path],
    tmp_path: Path,
) -> None:
    """A new file whose SHA-1 matches an existing Dump is linked
    (Dump.path updated) without orphaning the original.

    This exercises the create-link path used when an operator
    re-organises files on disk; the scanner picks up the new
    location and rebinds the existing Dump.
    """
    library, _release, original_rom = seeded_library_and_release
    new_location = original_rom.parent / "subdir" / "Sonic-relocated.md"
    new_location.parent.mkdir(parents=True, exist_ok=True)
    new_location.write_bytes(b"\x00" * 4096)

    # Pin the seeded Dump's sha1 to match the file's actual hash so
    # the link path fires deterministically.
    from romarr.identification.hasher import Hasher

    real_hash = Hasher().hash_path(new_location)
    dump = (
        await async_session.execute(select(Dump).limit(1))
    ).scalar_one()
    dump.sha1 = real_hash.sha1
    await async_session.commit()
    dump_id = dump.id
    await async_session.close()

    scanner = IncrementalScanner(
        sessionmaker=async_sessionmaker_factory,
        library_id=library.id,
        library_path=Path(library.path),
        accepted_extensions={".md"},
    )

    await scanner.handle_created(new_location)

    async with async_sessionmaker_factory() as fresh:
        refreshed = (
            await fresh.execute(select(Dump).where(Dump.id == dump_id))
        ).scalar_one()
        assert refreshed.path == str(new_location)
    assert scanner.counters.created_linked == 1
