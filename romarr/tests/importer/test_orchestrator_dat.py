"""Orchestrator DAT-match IDENTIFY fallback (slice 308).

When the filename parser fails to find a unique Game match but we
have a SHA-1 and a platform_id (e.g., from the header reader),
the orchestrator falls back to the local DAT cache. A
high-authority DAT entry (No-Intro > Redump > TOSEC) often
carries the canonical Game name, which resolves against the
catalogue.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus
from romarr.domain.models import DatEntry, Game, Platform, UnidentifiedDump
from romarr.identification.hasher import Hasher
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext


@pytest.mark.asyncio
async def test_dat_match_fallback_pins_game_when_filename_misses(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """The filename ``rom.bin`` doesn't match any Game by title,
    but the SHA-1 hits a local DAT entry whose name is "Sonic
    the Hedgehog" — that's used to resolve the suggested_game_id.
    """
    # Seed Mega Drive platform + a "Sonic the Hedgehog" Game.
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    game = Game(
        platform_id=platform.id,
        slug="sonic-mdat",
        title="Sonic the Hedgehog",
    )
    async_session.add(game)
    await async_session.commit()
    await async_session.refresh(game)

    # Build a Mega Drive ROM (header read pins platform_id).
    rom = tmp_path / "downloads" / "rom.bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom.write_bytes(bytes(body))

    # Compute the actual SHA-1 so the DAT entry below points at
    # the same bytes the orchestrator hashes.
    actual_sha1 = Hasher().hash_path(rom).sha1

    dat_entry = DatEntry(
        platform_id=platform.id,
        source="no-intro",
        name="Sonic the Hedgehog",
        sha1=actual_sha1,
        status=DumpStatus.VERIFIED,
        dat_contents_hash="x" * 64,
    )
    async_session.add(dat_entry)
    await async_session.commit()

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    await run_import(context, session=async_session)

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    assert parked.suggested_platform_id == platform.id
    assert parked.suggested_game_id == game.id


@pytest.mark.asyncio
async def test_dat_miss_leaves_suggested_game_id_null(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """No DAT entry for the SHA-1 + filename also doesn't match
    a Game → suggested_game_id stays NULL."""
    platform = Platform(slug="megadrive-miss", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    rom = tmp_path / "downloads" / "rom-no-dat.bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")
    body.extend(b"\x00" * (0x200 - len(body)))
    rom.write_bytes(bytes(body))

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    await run_import(context, session=async_session)

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    assert parked.suggested_game_id is None
