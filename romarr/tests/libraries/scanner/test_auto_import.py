"""Tests for the scanner's auto-ingest of unmatched files."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Dump, Game, Platform, PlatformFormat, Release
from romarr.identification.hasher import Hasher
from romarr.libraries.scanner.auto_import import (
    _slugify,
    auto_ingest_file,
)


async def _seed_gb_platform(session: AsyncSession) -> int:
    """Insert a GB platform with .gb as its only extension."""
    p = Platform(
        slug="gb",
        name="Nintendo Game Boy",
        short_name="GB",
        manufacturer="Nintendo",
        release_year=1989,
    )
    session.add(p)
    await session.flush()
    session.add(
        PlatformFormat(
            platform_id=p.id,
            extension=".gb",
            format_type="cartridge",
            pack_source="builtin",
        )
    )
    await session.commit()
    return p.id


def test_slugify_basic() -> None:
    assert _slugify("Pokemon - Red Version") == "pokemon-red-version"
    assert _slugify("Zelda: A Link to the Past") == "zelda-a-link-to-the-past"
    assert _slugify("   ") == "untitled"


@pytest.mark.asyncio
async def test_auto_ingest_creates_game_release_dump(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Fresh unmatched file → Game + Release + Dump land in the DB
    with the parsed filename as the title, no DAT match required."""
    await _seed_gb_platform(async_session)

    rom_path = tmp_path / "Pokemon - Red Version (USA).gb"
    rom_path.write_bytes(b"\x00" * 512)
    hash_result = Hasher().hash_path(rom_path)

    outcome = await auto_ingest_file(
        async_session,
        file_path=rom_path,
        hash_result=hash_result,
        library_id=None,
        size_bytes=512,
    )
    await async_session.commit()

    assert outcome.status == "ingested"
    assert outcome.game_id is not None
    assert outcome.dat_verified is False  # no DAT ingested

    game = (
        await async_session.execute(
            select(Game).where(Game.id == outcome.game_id)
        )
    ).scalar_one()
    # Title comes from the parsed filename (region stripped).
    assert "Pokemon" in game.title
    assert game.slug == _slugify(game.title)
    assert game.platform_id is not None
    assert game.needs_metadata_refresh is True

    release = (
        await async_session.execute(
            select(Release).where(Release.id == outcome.release_id)
        )
    ).scalar_one()
    assert release.game_id == game.id
    assert "US" in release.regions

    dump = (
        await async_session.execute(
            select(Dump).where(Dump.id == outcome.dump_id)
        )
    ).scalar_one()
    assert dump.sha1 == hash_result.sha1
    assert dump.imported_via == "scan"


@pytest.mark.asyncio
async def test_auto_ingest_skips_unknown_extension(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """No platform registered for the extension → skipped, no rows."""
    await _seed_gb_platform(async_session)

    rom_path = tmp_path / "mystery.wat"
    rom_path.write_bytes(b"\x00" * 128)
    hash_result = Hasher().hash_path(rom_path)

    outcome = await auto_ingest_file(
        async_session,
        file_path=rom_path,
        hash_result=hash_result,
        library_id=None,
        size_bytes=128,
    )

    assert outcome.status == "skipped"
    assert outcome.game_id is None
    assert "no platform" in (outcome.reason or "")


@pytest.mark.asyncio
async def test_auto_ingest_dedups_game_across_files(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Two files → same parsed title → one Game, two Releases (if
    the release names differ) or reuses everything."""
    await _seed_gb_platform(async_session)

    rom_a = tmp_path / "Tetris (USA).gb"
    rom_a.write_bytes(b"\x00" * 256)
    rom_b = tmp_path / "Tetris (Europe).gb"
    rom_b.write_bytes(b"\x01" * 256)

    hasher = Hasher()
    out_a = await auto_ingest_file(
        async_session,
        file_path=rom_a,
        hash_result=hasher.hash_path(rom_a),
        library_id=None,
        size_bytes=256,
    )
    out_b = await auto_ingest_file(
        async_session,
        file_path=rom_b,
        hash_result=hasher.hash_path(rom_b),
        library_id=None,
        size_bytes=256,
    )
    await async_session.commit()

    assert out_a.status == "ingested"
    assert out_b.status == "ingested"
    # Same Game (dedup by platform+slug).
    assert out_a.game_id == out_b.game_id
    # Different Releases if the release names differ.
    assert out_a.release_id != out_b.release_id


@pytest.mark.asyncio
async def test_auto_ingest_rescan_reuses_dump(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Second call on the same path → path-unique Dump reused,
    not duplicated (FR-005)."""
    await _seed_gb_platform(async_session)

    rom = tmp_path / "Same Game (USA).gb"
    rom.write_bytes(b"\x00" * 256)
    hasher = Hasher()
    hr = hasher.hash_path(rom)

    out_1 = await auto_ingest_file(
        async_session,
        file_path=rom,
        hash_result=hr,
        library_id=None,
        size_bytes=256,
    )
    out_2 = await auto_ingest_file(
        async_session,
        file_path=rom,
        hash_result=hr,
        library_id=None,
        size_bytes=256,
    )
    await async_session.commit()

    assert out_1.dump_id == out_2.dump_id
    dumps = (
        await async_session.execute(
            select(Dump).where(Dump.path == str(rom))
        )
    ).scalars().all()
    assert len(dumps) == 1
