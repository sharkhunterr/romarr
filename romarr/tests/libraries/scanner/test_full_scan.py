"""Full-scan integration tests (T036, T037, T038)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, Release
from romarr.identification.hasher import Hasher
from romarr.libraries.models import Library
from romarr.libraries.scanner import full_scan, walk_library
from romarr.libraries.scanner.progress import ScanProgressEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_rom_file(tmp_path: Path) -> Callable[[str, bytes], Path]:
    """Drop a fake ROM file and return its path."""

    def _make(rel_path: str, body: bytes = b"\x00\x01\x02\x03ROM-DATA") -> Path:
        path = tmp_path / "library" / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    return _make


@pytest.fixture
def hash_of(make_rom_file: Callable[[str, bytes], Path]) -> Callable[[bytes], dict]:
    """Compute hashes for a known body so tests can pre-populate
    matching Dump rows without depending on the live filesystem."""
    hasher = Hasher()

    def _hash(body: bytes) -> dict:
        # Hash via a dummy file so we exercise the same code path.
        from io import BytesIO

        return hasher.hash_stream(BytesIO(body)).as_dict()

    return _hash


@pytest.fixture
async def seeded_library(
    async_session: AsyncSession, tmp_path: Path
) -> Library:
    from tests.libraries.conftest import seeded_profile_ids  # noqa: F401

    # Build a library row anchored at <tmp_path>/library.
    library_root = tmp_path / "library"
    library_root.mkdir()

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
    return library


async def _seed_minimal_profiles(session: AsyncSession) -> dict[str, int]:
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    quality = QualityProfile(
        name="quality-default",
        allowed_formats=["raw", "zip", "7z"],
        preferred_format="7z",
        require_dat_verified=False,
        upgrade_until_format="7z",
    )
    region = RegionProfile(
        name="region-default",
        priorities=["USA"],
        allow_fallback_outside_priorities=True,
        exclude_regions=[],
    )
    dump = DumpProfile(
        name="dump-default",
        allowed_dump_status=["verified"],
        allow_proto_beta=False,
        allow_hacks=False,
        allow_trainers=False,
        allow_translations=False,
    )
    language = LanguageProfile(
        name="language-default",
        required_languages=[],
        preferred_languages=["en"],
        exclude_japanese_only=False,
    )
    naming = NamingProfile(
        name="naming-default",
        convention="no-intro",
        template="{{ game.title }} ({{ release.region }})",
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


async def _seed_release(
    session: AsyncSession,
    *,
    library: Library,
    title: str = "Sonic the Hedgehog",
    slug: str = "sonic",
) -> Release:
    platform = Platform(name="Mega Drive", slug=f"megadrive-{slug}")
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    game = Game(platform_id=platform.id, slug=slug, title=title)
    session.add(game)
    await session.commit()
    await session.refresh(game)

    release = Release(
        game_id=game.id,
        name=f"{title} (USA)",
        regions=["USA"],
        languages=["en"],
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
        library_id=library.id,
        status="wanted",
    )
    session.add(release)
    await session.commit()
    await session.refresh(release)
    return release


# ---------------------------------------------------------------------------
# walk_library
# ---------------------------------------------------------------------------


def test_walk_library_filters_by_extension(
    tmp_path: Path, make_rom_file: Callable[[str, bytes], Path]
) -> None:
    make_rom_file("megadrive/sonic.md", b"a")
    make_rom_file("megadrive/streets.gen", b"b")
    make_rom_file("notes.txt", b"c")  # not a ROM extension
    make_rom_file("nested/deep/altered.md", b"d")

    found = sorted(
        p.name
        for p in walk_library(
            tmp_path / "library", accepted_extensions={".md", "gen"}
        )
    )
    assert found == ["altered.md", "sonic.md", "streets.gen"]


def test_walk_library_case_insensitive(
    tmp_path: Path, make_rom_file: Callable[[str, bytes], Path]
) -> None:
    make_rom_file("UPPER.MD", b"a")
    found = list(
        walk_library(tmp_path / "library", accepted_extensions={"md"})
    )
    assert len(found) == 1


# ---------------------------------------------------------------------------
# T036 — link existing Release by hash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_links_existing_release_via_hash_match(
    async_session: AsyncSession,
    seeded_library: Library,
    make_rom_file: Callable[[str, bytes], Path],
    hash_of: Callable[[bytes], dict],
) -> None:
    """A Dump pre-seeded under a different (or stale) path is
    re-bound to the on-disk file when the hash matches."""
    body = b"sonic-rom-bytes" * 1024
    rom = make_rom_file("megadrive/sonic.md", body)
    h = hash_of(body)

    release = await _seed_release(async_session, library=seeded_library)
    pre_seeded_dump = Dump(
        release_id=release.id,
        path="/old/path/sonic.md",  # different from on-disk
        original_filename="sonic.md",
        size_bytes=h["size_bytes"],
        format="md",
        crc32=h["crc32"],
        md5=h["md5"],
        sha1=h["sha1"],
    )
    async_session.add(pre_seeded_dump)
    await async_session.commit()

    result = await full_scan(
        session=async_session,
        library_id=seeded_library.id,
        library_path=Path(seeded_library.path),
        accepted_extensions={".md"},
    )
    assert result.last_status == "success"
    assert result.files_processed == 1
    assert result.files_linked == 1
    assert result.files_unmatched == 0

    # The Dump was rebound to the on-disk path.
    rebound = (
        await async_session.execute(select(Dump).where(Dump.sha1 == h["sha1"]))
    ).scalar_one()
    assert rebound.path == str(rom)


# ---------------------------------------------------------------------------
# T037 — idempotent re-scan skips known (path, size)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_known_path_and_size(
    async_session: AsyncSession,
    seeded_library: Library,
    make_rom_file: Callable[[str, bytes], Path],
    hash_of: Callable[[bytes], dict],
) -> None:
    body = b"sonic-rom-bytes" * 64
    rom = make_rom_file("megadrive/sonic.md", body)
    h = hash_of(body)

    release = await _seed_release(async_session, library=seeded_library)
    async_session.add(
        Dump(
            release_id=release.id,
            path=str(rom),
            original_filename="sonic.md",
            size_bytes=h["size_bytes"],
            format="md",
            crc32=h["crc32"],
            md5=h["md5"],
            sha1=h["sha1"],
        )
    )
    await async_session.commit()

    result = await full_scan(
        session=async_session,
        library_id=seeded_library.id,
        library_path=Path(seeded_library.path),
        accepted_extensions={".md"},
    )
    assert result.files_seen == 1
    assert result.files_skipped == 1
    assert result.files_processed == 0
    assert result.files_unmatched == 0


# ---------------------------------------------------------------------------
# T038 — orphan detection marks Release wanted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_file_marks_release_wanted(
    async_session: AsyncSession,
    seeded_library: Library,
    hash_of: Callable[[bytes], dict],
) -> None:
    body = b"sonic-rom-bytes" * 64
    h = hash_of(body)

    release = await _seed_release(async_session, library=seeded_library)
    release.status = "imported"
    release.cutoff_met = True
    async_session.add(
        Dump(
            release_id=release.id,
            path="/nonexistent/sonic.md",
            original_filename="sonic.md",
            size_bytes=h["size_bytes"],
            format="md",
            crc32=h["crc32"],
            md5=h["md5"],
            sha1=h["sha1"],
        )
    )
    await async_session.commit()
    release_id = release.id

    result = await full_scan(
        session=async_session,
        library_id=seeded_library.id,
        library_path=Path(seeded_library.path),
        accepted_extensions={".md"},
    )

    assert result.files_orphaned == 1
    refreshed = (
        await async_session.execute(
            select(Release).where(Release.id == release_id)
        )
    ).scalar_one()
    assert refreshed.status == "wanted"
    assert refreshed.cutoff_met is False


# ---------------------------------------------------------------------------
# Unmatched files are counted, not silently dropped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmatched_file_counts_for_importer(
    async_session: AsyncSession,
    seeded_library: Library,
    make_rom_file: Callable[[str, bytes], Path],
) -> None:
    """A new file with a hash matching no Dump and no DAT entry is
    counted as ``unmatched`` so the operator can see the
    importer's pending workload."""
    make_rom_file("megadrive/unknown.md", b"unknown-rom-bytes")

    result = await full_scan(
        session=async_session,
        library_id=seeded_library.id,
        library_path=Path(seeded_library.path),
        accepted_extensions={".md"},
    )
    assert result.files_unmatched == 1
    assert result.files_linked == 0


# ---------------------------------------------------------------------------
# Progress events surface on the sink
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_scan_emits_progress_events(
    async_session: AsyncSession,
    seeded_library: Library,
    make_rom_file: Callable[[str, bytes], Path],
) -> None:
    for i in range(5):
        make_rom_file(f"megadrive/rom-{i}.md", f"body-{i}".encode())

    captured: list[ScanProgressEvent] = []
    result = await full_scan(
        session=async_session,
        library_id=seeded_library.id,
        library_path=Path(seeded_library.path),
        accepted_extensions={".md"},
        progress_sink=captured.append,
        progress_every=2,
    )
    # 5 files / every=2 → modulo emits at 2, 4, plus the final
    # snapshot from .finish() → 3 events minimum.
    assert len(captured) >= 3
    # The last event always carries the terminal counters.
    final = captured[-1]
    assert final.files_seen == 5
    assert result.files_unmatched == 5


# ---------------------------------------------------------------------------
# T034 — perf gate: 100 small ROMs scanned in < 5 s (SC-003 first leg)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_100_files_under_5s(
    async_session: AsyncSession,
    seeded_library: Library,
    make_rom_file: Callable[[str, bytes], Path],
) -> None:
    """100 small ROMs scan in under 5 seconds.

    Spec 009 SC-003 first leg. The hashing path dominates the
    runtime — each file is a few hundred bytes, so the bound
    is dictated by per-file SQLAlchemy inserts + the
    streaming hasher's setup cost. On a modern dev box this
    completes in < 1 s; the 5 s budget gives headroom for
    SQLite / disk variability in CI.
    """
    import time

    for i in range(100):
        make_rom_file(f"megadrive/rom-{i:03d}.md", f"body-{i}-pad".encode())

    started = time.monotonic()
    result = await full_scan(
        session=async_session,
        library_id=seeded_library.id,
        library_path=Path(seeded_library.path),
        accepted_extensions={".md"},
    )
    elapsed = time.monotonic() - started

    # No pre-seeded Dumps + no DAT cascade in this test → every
    # discovered file lands in `files_unmatched`. files_seen is
    # the canonical "discovered N files" counter for the perf
    # gate; the importer picks up unmatched files separately.
    assert result.files_seen == 100
    assert result.files_unmatched == 100
    assert result.last_status == "success"
    assert elapsed < 5.0, (
        f"100-file full scan took {elapsed:.2f}s; SC-003 budget is 5.0s"
    )


# ---------------------------------------------------------------------------
# T035 — perf gate: 10 000 files scan in < 5 min (SC-003 second leg)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_10k_files_under_5min(
    async_session: AsyncSession,
    seeded_library: Library,
    make_rom_file: Callable[[str, bytes], Path],
) -> None:
    """10 000 tiny synthetic files scan in under 5 minutes.

    Spec 009 SC-003 second leg. The hashing path is per-file
    work; SQLAlchemy bulk inserts dominate the persistence
    side. On a modern dev box this completes in ~2 s; the
    300 s budget gives substantial CI headroom.
    """
    import time

    for i in range(10_000):
        # Distribute across 100 sub-folders so the directory
        # walker exercises os.scandir on a non-trivial tree.
        bucket = i // 100
        make_rom_file(
            f"megadrive/bucket-{bucket:03d}/rom-{i:05d}.md",
            f"body-{i}".encode(),
        )

    started = time.monotonic()
    result = await full_scan(
        session=async_session,
        library_id=seeded_library.id,
        library_path=Path(seeded_library.path),
        accepted_extensions={".md"},
    )
    elapsed = time.monotonic() - started

    assert result.files_seen == 10_000
    assert result.files_unmatched == 10_000
    assert result.last_status == "success"
    assert elapsed < 300.0, (
        f"10k-file full scan took {elapsed:.2f}s; SC-003 budget is 300.0s"
    )


# ---------------------------------------------------------------------------
# T040 — full-scan creates Release for unmatched files (delegates to importer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_file_creates_release(
    async_session: AsyncSession,
    seeded_library: Library,
    tmp_path: Path,
) -> None:
    """T040 / FR-014 — file not matching any Release → scanner
    delegates to the importer orchestrator. The orchestrator's
    fuzzy-match resolves the filename to the seeded Game; the
    in-place MOVE fast-path keeps the file under the library tree;
    auto-import creates a new Release+Dump."""
    from romarr.domain.models import Dump as DumpModel

    # Seed an unmonitored Game whose title fuzzy-matches the
    # filename below. Mega Drive header so the IDENTIFY cascade
    # locks the platform.
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-fullscan",
        title="Sonic the Hedgehog",
        monitored=True,
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    # Drop a Mega-Drive ROM directly under the library tree at the
    # right platform subfolder. The scanner walks `library_root`,
    # not the importer-watched downloads dir.
    library_root = Path(seeded_library.path)
    rom_dir = library_root / "megadrive"
    rom_dir.mkdir(parents=True, exist_ok=True)
    rom_path = rom_dir / "Sonic the Hedgehog (USA).md"
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom_path.write_bytes(bytes(body))

    result = await full_scan(
        session=async_session,
        library_id=seeded_library.id,
        library_path=library_root,
        accepted_extensions={".md"},
        create_release_for_unmatched=True,
    )
    assert result.last_status == "success"

    # The orchestrator's auto-import created a Release for the
    # matched Game and applied the library's naming profile — the
    # file is organised into a per-game subfolder
    # (``<platform>/<game title>/<file>``), the standard ROM
    # library layout.
    releases = (
        await async_session.execute(
            select(Release).where(Release.game_id == game.id)
        )
    ).scalars().all()
    assert len(releases) == 1
    new_release = releases[0]
    assert new_release.library_id == seeded_library.id

    dumps = (
        await async_session.execute(
            select(DumpModel).where(DumpModel.release_id == new_release.id)
        )
    ).scalars().all()
    assert len(dumps) == 1
    expected_dump_path = rom_dir / "Sonic the Hedgehog" / "Sonic the Hedgehog (USA).md"
    assert dumps[0].path == str(expected_dump_path)
    # The file physically lives at the naming-profile target path.
    assert expected_dump_path.is_file()
