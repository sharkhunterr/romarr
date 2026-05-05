"""Orchestrator EXTRACT-step integration (slice 302).

When the source file is an archive (.zip / .7z / .rar) the
orchestrator runs it through the EXTRACT step before hashing.
A parkable ExtractError (bad-archive / depth-exceeded /
bomb-detected) is recorded as the parked
``unidentified_dump.rejection_reason`` so the operator's
triage UI surfaces the right taxonomy hit.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import UnidentifiedDump
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext, RejectionReason


@pytest.mark.asyncio
async def test_bad_archive_parks_with_extract_bad_archive_reason(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """A corrupt .zip file → park with ``extract:bad-archive``."""
    archive = tmp_path / "downloads" / "broken.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"this is not a zip file")

    context = ImportContext(
        source_path=archive,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is False
    assert outcome.rejection_reason == RejectionReason.EXTRACT_BAD_ARCHIVE

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(
                UnidentifiedDump.path == str(archive)
            )
        )
    ).scalar_one()
    assert parked.rejection_reason == "extract:bad-archive"
    assert parked.last_error is not None


@pytest.mark.asyncio
async def test_valid_zip_advances_to_match_no_game(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """A well-formed .zip containing a ROM extracts successfully;
    the orchestrator continues with the extracted file and parks
    as ``match:no_game`` (the audit-only fall-through).

    The parked row's path points at the EXTRACTED file, not the
    archive — the operator's manual-match UI works against the
    actual ROM."""
    archive = tmp_path / "downloads" / "Sonic.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    rom_name = "Sonic the Hedgehog (USA).md"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(rom_name, b"\x00" * 4096)

    context = ImportContext(
        source_path=archive,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is False
    assert outcome.rejection_reason == RejectionReason.NO_GAME_MATCH

    # Parked row points at the extracted ROM, not the archive.
    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(
                UnidentifiedDump.rejection_reason == "match:no_game"
            )
        )
    ).scalar_one()
    assert parked.path.endswith(rom_name)
    assert parked.size_bytes == 4096


@pytest.mark.asyncio
async def test_non_archive_skips_extract_step(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """A ``.md`` ROM is hashed directly — no extract attempt."""
    rom = tmp_path / "downloads" / "Sonic.md"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(b"\x00" * 1024)

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.rejection_reason == RejectionReason.NO_GAME_MATCH

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one()
    assert parked.size_bytes == 1024
    assert parked.sha1 is not None  # hashed
