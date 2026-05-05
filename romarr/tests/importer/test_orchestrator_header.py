"""Orchestrator HEADER-read IDENTIFY enrichment (slice 307).

The orchestrator's IDENTIFY step now runs the registered header
readers (iNES / MegaDrive / ISO9660) before the filename parser.
A header hit pins ``suggested_platform_id`` even when the
filename is uninformative.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Platform, UnidentifiedDump
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext


@pytest.mark.asyncio
async def test_megadrive_header_pins_suggested_platform_id(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """A Mega Drive ROM (system identifier ``SEGA MEGA DRIVE`` at
    offset $100) → ``suggested_platform_id`` resolves to the
    seeded Mega Drive Platform regardless of filename."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    rom = tmp_path / "downloads" / "uninformative-name.bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    # Pad to the offset where the system identifier lives + write
    # ``SEGA MEGA DRIVE`` aligned to $100.
    body = bytearray(b"\x00" * 0x100)
    body.extend(b"SEGA MEGA DRIVE ")  # 16-byte system identifier
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
    assert parked.suggested_platform_id == platform.id


@pytest.mark.asyncio
async def test_ines_header_pins_suggested_platform_id(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """An iNES file (``NES\\x1a`` magic + 16-byte header) → NES."""
    platform = Platform(slug="nes", name="NES")
    async_session.add(platform)
    await async_session.commit()
    await async_session.refresh(platform)

    rom = tmp_path / "downloads" / "rom.bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    body = bytearray(b"NES\x1a")  # magic
    body.extend(b"\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")  # 12 more
    body.extend(b"\x00" * 1024)  # PRG ROM
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
    assert parked.suggested_platform_id == platform.id


@pytest.mark.asyncio
async def test_unknown_format_leaves_suggested_platform_id_null(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When no header reader recognizes the file AND the filename
    has no convention hint, ``suggested_platform_id`` stays NULL."""
    rom = tmp_path / "downloads" / "mystery.bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(b"\x42" * 4096)  # arbitrary garbage

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
    assert parked.suggested_platform_id is None
