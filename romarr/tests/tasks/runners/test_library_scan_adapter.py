"""LibraryScanAdapter integration tests (slice 209 / spec 012
catalogue closure).

Each test seeds a Library row + matching PlatformFormat
entries, drops a sample file in a tmp directory, and asserts
the adapter's JobResult summary reports the expected counts.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.models import (
    Game,
    Platform,
    PlatformFormat,
    Release,
)
from romarr.libraries.models import Library, LibraryPlatform
from romarr.profiles.models import (
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)
from romarr.tasks.runners.adapters import LibraryScanAdapter


def _fake_context(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None,
    parameters: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="LibraryScan",
        job_run_id=1,
        triggered_by=SimpleNamespace(value="cron"),
        sessionmaker=sessionmaker,
        parameters=parameters or {},
    )


async def _seed_profiles(
    sm: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    async with sm() as session:
        rows = [
            QualityProfile(
                name="quality-default",
                allowed_formats=["raw"],
                preferred_format="raw",
                require_dat_verified=False,
                upgrade_until_format="raw",
            ),
            RegionProfile(
                name="region-default",
                priorities=["USA"],
                allow_fallback_outside_priorities=True,
                exclude_regions=[],
            ),
            DumpProfile(
                name="dump-default",
                allowed_dump_status=["verified"],
                allow_proto_beta=False,
                allow_hacks=False,
                allow_trainers=False,
                allow_translations=False,
            ),
            LanguageProfile(
                name="language-default",
                required_languages=[],
                preferred_languages=["en"],
                exclude_japanese_only=False,
            ),
            NamingProfile(
                name="naming-default",
                convention="no-intro",
                template="{{ game.title }}",
            ),
        ]
        session.add_all(rows)
        await session.commit()
        return {
            "quality_profile_id": rows[0].id,
            "region_profile_id": rows[1].id,
            "dump_profile_id": rows[2].id,
            "language_profile_id": rows[3].id,
            "naming_profile_id": rows[4].id,
        }


async def _seed_platform_with_format(
    sm: async_sessionmaker[AsyncSession],
    *,
    slug: str = "md",
    extension: str = ".md",
) -> int:
    async with sm() as session:
        platform = Platform(slug=slug, name=slug.upper())
        session.add(platform)
        await session.flush()
        session.add(
            PlatformFormat(
                platform_id=platform.id,
                extension=extension,
                format_type="cartridge",
            )
        )
        await session.commit()
        return platform.id


async def _seed_library(
    sm: async_sessionmaker[AsyncSession],
    *,
    library_path: Path,
    profile_ids: dict[str, int],
    name: str = "My Library",
    platforms_restricted: bool = False,
    allowed_platform_id: int | None = None,
) -> int:
    async with sm() as session:
        lib = Library(
            name=name,
            path=str(library_path),
            lifecycle_policy="hardlink_and_seed",
            min_disk_free_gb=1,
            platforms_restricted=platforms_restricted,
            **profile_ids,
        )
        session.add(lib)
        await session.flush()
        if allowed_platform_id is not None:
            session.add(
                LibraryPlatform(
                    library_id=lib.id,
                    platform_id=allowed_platform_id,
                )
            )
        await session.commit()
        return lib.id


@pytest.mark.asyncio
async def test_adapter_falls_back_without_sessionmaker() -> None:
    adapter = LibraryScanAdapter()
    context = _fake_context(sessionmaker=None)
    result = await adapter._run(context)
    assert result.summary["stub"] is True


@pytest.mark.asyncio
async def test_adapter_scans_every_library_when_no_id_param(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """No ``libraryId`` parameter → all configured Libraries
    get a full scan. Empty filesystem → zero files seen but
    the round still counts as scanned."""
    sm = async_sessionmaker_factory
    profile_ids = await _seed_profiles(sm)
    await _seed_platform_with_format(sm)
    lib_path = tmp_path / "library"
    lib_path.mkdir()
    await _seed_library(
        sm, library_path=lib_path, profile_ids=profile_ids
    )

    adapter = LibraryScanAdapter()
    context = _fake_context(sessionmaker=sm)
    result = await adapter._run(context)
    assert result.summary["libraries_scanned"] == 1
    assert result.summary["libraries_skipped"] == 0
    per_lib = result.summary["per_library"][0]
    assert per_lib["files_seen"] == 0


@pytest.mark.asyncio
async def test_adapter_processes_a_real_file(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """Drop a real ``.md`` file → scanner walks it, counts as
    unmatched (no Dump pre-exists for that hash)."""
    sm = async_sessionmaker_factory
    profile_ids = await _seed_profiles(sm)
    await _seed_platform_with_format(sm)
    lib_path = tmp_path / "library"
    lib_path.mkdir()
    rom = lib_path / "Sonic.md"
    rom.write_bytes(b"\x00" * 1024)
    await _seed_library(
        sm, library_path=lib_path, profile_ids=profile_ids
    )

    adapter = LibraryScanAdapter()
    context = _fake_context(sessionmaker=sm)
    result = await adapter._run(context)
    per_lib = result.summary["per_library"][0]
    # The file is new (no pre-existing Dump) → counted as
    # unmatched for the importer to pick up.
    assert per_lib["files_seen"] == 1
    assert per_lib["files_unmatched"] == 1


@pytest.mark.asyncio
async def test_adapter_respects_libraryId_parameter(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """When ``libraryId`` is supplied, only that one library
    is scanned (the others are ignored)."""
    sm = async_sessionmaker_factory
    profile_ids = await _seed_profiles(sm)
    await _seed_platform_with_format(sm)
    lib_a = tmp_path / "a"; lib_a.mkdir()
    lib_b = tmp_path / "b"; lib_b.mkdir()
    id_a = await _seed_library(
        sm, library_path=lib_a, profile_ids=profile_ids, name="Lib A"
    )
    await _seed_library(
        sm, library_path=lib_b, profile_ids=profile_ids, name="Lib B"
    )

    adapter = LibraryScanAdapter()
    context = _fake_context(
        sessionmaker=sm, parameters={"libraryId": id_a}
    )
    result = await adapter._run(context)
    assert result.summary["libraries_scanned"] == 1
    assert len(result.summary["per_library"]) == 1
    assert result.summary["per_library"][0]["library_id"] == id_a


@pytest.mark.asyncio
async def test_adapter_skips_missing_path(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """A Library whose ``path`` doesn't exist → skipped with
    ``reason='path_missing'``. Common after an unmounted
    network share."""
    sm = async_sessionmaker_factory
    profile_ids = await _seed_profiles(sm)
    await _seed_platform_with_format(sm)
    await _seed_library(
        sm,
        library_path=tmp_path / "does-not-exist",
        profile_ids=profile_ids,
    )

    adapter = LibraryScanAdapter()
    context = _fake_context(sessionmaker=sm)
    result = await adapter._run(context)
    assert result.summary["libraries_scanned"] == 0
    assert result.summary["libraries_skipped"] == 1
    per_lib = result.summary["per_library"][0]
    assert per_lib["skipped"] is True
    assert per_lib["reason"] == "path_missing"


@pytest.mark.asyncio
async def test_adapter_uses_per_library_allowlist_when_restricted(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """``platforms_restricted=True`` → only the allowlist's
    PlatformFormat extensions count. A file in the library
    matching an OUT-OF-LIST platform must NOT show up."""
    sm = async_sessionmaker_factory
    profile_ids = await _seed_profiles(sm)
    md_id = await _seed_platform_with_format(
        sm, slug="md", extension=".md"
    )
    # Add a SECOND platform with a different extension.
    await _seed_platform_with_format(
        sm, slug="snes", extension=".sfc"
    )
    lib_path = tmp_path / "library"
    lib_path.mkdir()
    # File matching the SNES extension — should NOT count.
    (lib_path / "smw.sfc").write_bytes(b"\x00" * 1024)
    # File matching the MD extension — should count.
    (lib_path / "sonic.md").write_bytes(b"\x00" * 1024)
    await _seed_library(
        sm,
        library_path=lib_path,
        profile_ids=profile_ids,
        platforms_restricted=True,
        allowed_platform_id=md_id,
    )

    adapter = LibraryScanAdapter()
    context = _fake_context(sessionmaker=sm)
    result = await adapter._run(context)
    per_lib = result.summary["per_library"][0]
    # Only the .md file made it through the extension filter.
    assert per_lib["files_seen"] == 1
