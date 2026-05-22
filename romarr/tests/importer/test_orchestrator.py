"""Tests for the minimal happy-path orchestrator (slice 288).

The orchestrator drives the audit chain end-to-end for the
no-game-match path: hash → park → write history row →
return outcome. Subsequent slices (GAMEMATCH / PROFILEGATE /
RENDER / MOVE / DBUPDATE / LIFECYCLE / NOTIFY) layer real
matching + persistence on top; this test pins the audit
contract today.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import UnidentifiedDump
from romarr.importer.models import ImportHistory
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext, RejectionReason


def _make_rom(tmp_path: Path) -> Path:
    src = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 4096)
    return src


@pytest.mark.asyncio
async def test_run_import_writes_failure_history_row(
    async_session: AsyncSession, base_context: ImportContext
) -> None:
    """Every input today produces a ``success=False`` history
    row carrying the correlation id + duration."""
    outcome = await run_import(base_context, session=async_session)

    assert outcome.success is False
    assert outcome.history_id > 0
    assert outcome.correlation_id == base_context.correlation_id
    assert outcome.duration_ms >= 0
    assert outcome.rejection_reason == RejectionReason.NO_GAME_MATCH

    rows = (
        await async_session.execute(
            select(ImportHistory).where(
                ImportHistory.id == outcome.history_id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    history = rows[0]
    assert history.success is False
    assert history.error_msg == RejectionReason.NO_GAME_MATCH.value
    assert history.imported_via == "manual"


@pytest.mark.asyncio
async def test_run_import_parks_existing_file_in_unidentified(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When the source file exists, the orchestrator hashes it
    AND parks it in ``unidentified_dump`` so the operator can
    triage via the manual-match endpoint."""
    from uuid import uuid4

    rom = _make_rom(tmp_path)
    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is False

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(
                UnidentifiedDump.path == str(rom),
            )
        )
    ).scalar_one_or_none()
    assert parked is not None
    assert parked.rejection_reason == "match:no_game"
    assert parked.sha1 is not None
    assert parked.size_bytes == 4096


@pytest.mark.asyncio
async def test_run_import_handles_missing_source_path(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When the source file doesn't exist (rename mid-pipeline,
    operator deleted, …) the orchestrator still writes a
    history row — it must not raise."""
    from uuid import uuid4

    missing = tmp_path / "nope" / "ghost.md"
    context = ImportContext(
        source_path=missing,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)

    assert outcome.success is False
    assert outcome.history_id > 0
    # The park branch is skipped (size_bytes == 0); the history
    # row is still written.
    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(
                UnidentifiedDump.path == str(missing),
            )
        )
    ).scalar_one_or_none()
    assert parked is None


@pytest.mark.asyncio
async def test_run_import_persists_suggested_game_id_when_unique_title_match(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """The IDENTIFY enrichment step (slice 296) populates
    ``suggested_game_id`` on the parked row when the filename
    parser produces a high-confidence title that matches exactly
    one Game in the catalogue. The operator's manual-match UI uses
    this hint to one-click the right Game."""
    from uuid import uuid4

    from romarr.domain.models import Game, Platform

    platform = Platform(slug="megadrive", name="Mega Drive", manufacturer="Sega")
    async_session.add(platform)
    await async_session.flush()

    game = Game(
        platform_id=platform.id,
        slug="sonic-the-hedgehog",
        title="Sonic the Hedgehog",
    )
    async_session.add(game)
    await async_session.flush()

    rom = _make_rom(tmp_path)
    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)
    assert outcome.success is False

    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(
                UnidentifiedDump.path == str(rom),
            )
        )
    ).scalar_one()
    assert parked.suggested_game_id == game.id


@pytest.mark.asyncio
async def test_run_import_records_correlation_id_and_outcome_shape(
    async_session: AsyncSession, base_context: ImportContext
) -> None:
    outcome = await run_import(base_context, session=async_session)

    # ImportOutcome shape contract: success / coalesced /
    # dest_path / dump_id / release_id / game_id / confidence
    # / warning / error_msg / rejection_reason / history_id /
    # correlation_id / duration_ms.
    assert outcome.success is False
    assert outcome.coalesced is False
    assert outcome.dest_path is None
    assert outcome.dump_id is None
    assert outcome.release_id is None
    assert outcome.game_id is None
    assert outcome.confidence is None
    assert outcome.warning is None
    assert outcome.error_msg == RejectionReason.NO_GAME_MATCH.value
    assert outcome.rejection_reason == RejectionReason.NO_GAME_MATCH


@pytest.mark.asyncio
async def test_run_import_coalesces_when_hash_already_imported(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When GAMEMATCH can't tie a file to a game but its SHA-1 is
    already a known imported Dump — a leftover archive the watcher
    re-dispatched, a meta-torrent plus a standalone grab of the
    same ROM — the orchestrator coalesces it as a success instead
    of parking a bogus match:no_game failure."""
    from uuid import uuid4

    from romarr.domain.models import Dump, Game, Platform, Release
    from romarr.identification.hasher import Hasher

    rom = _make_rom(tmp_path)
    sha1 = Hasher().hash_path(rom).sha1

    platform = Platform(slug="megadrive", name="Mega Drive", manufacturer="Sega")
    async_session.add(platform)
    await async_session.flush()
    # A game whose title does NOT match the ROM filename, so
    # GAMEMATCH leaves monitored_game_id unset and the run heads
    # for the match:no_game park path.
    game = Game(
        platform_id=platform.id,
        slug="some-other-game",
        title="Some Other Game",
    )
    async_session.add(game)
    await async_session.flush()
    release = Release(
        game_id=game.id, name="Some Other Game (USA)", status="imported"
    )
    async_session.add(release)
    await async_session.flush()
    # The decisive seed: a Dump already carrying the ROM's SHA-1.
    async_session.add(
        Dump(
            release_id=release.id,
            path="/library/roms/md/Some Other Game/Some Other Game (USA).md",
            original_filename="Some Other Game (USA).md",
            size_bytes=4096,
            format="md",
            crc32="00000000",
            md5="0" * 32,
            sha1=sha1,
        )
    )
    await async_session.flush()

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="manual",
    )
    outcome = await run_import(context, session=async_session)

    # Coalesced success — NOT a match:no_game failure.
    assert outcome.success is True
    assert outcome.coalesced is True
    assert outcome.rejection_reason is None

    # No bogus failure history row, and nothing parked.
    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == str(rom))
        )
    ).scalar_one_or_none()
    assert parked is None
