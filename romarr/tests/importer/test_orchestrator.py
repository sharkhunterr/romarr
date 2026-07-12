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


@pytest.mark.asyncio
async def test_run_import_coalesces_when_source_vanished_after_sibling_import(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """qBit fires two events for one logical torrent: a generic
    ``/downloads`` directory-scan plus a per-torrent completion.
    The first wins the race, extracts + hashes + imports + DELETES
    the source. The second arrives moments later, finds the source
    missing, can't hash it (so the sha1-based coalesce can't fire),
    and would otherwise be parked as a bogus ``match:no_game``.

    A filename-stem coalesce against any recently-imported Dump
    catches it. Stem normalisation tolerates qBit's
    ``(USA)`` → ``_USA_`` mangling and the archive→ROM
    extension change."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from romarr.domain.models import Dump, Game, Platform, Release

    platform = Platform(slug="n64", name="Nintendo 64", manufacturer="Nintendo")
    async_session.add(platform)
    await async_session.flush()
    game = Game(
        platform_id=platform.id,
        slug="castlevania-lod",
        title="Castlevania - Legacy of Darkness",
    )
    async_session.add(game)
    await async_session.flush()
    release = Release(
        game_id=game.id,
        name="Castlevania - Legacy of Darkness (USA)",
        status="imported",
    )
    async_session.add(release)
    await async_session.flush()
    async_session.add(
        Dump(
            release_id=release.id,
            path="/library/roms/n64/Castlevania/Castlevania - Legacy of Darkness (USA).z64",
            original_filename="Castlevania - Legacy of Darkness (USA).z64",
            size_bytes=4096,
            format="z64",
            crc32="00000000",
            md5="0" * 32,
            sha1="0" * 40,
            imported_at=datetime.now(UTC),
        )
    )
    await async_session.flush()

    # The qBit-mangled archive name the LATE event sees — never
    # exists on disk (the sibling import already deleted it).
    vanished = tmp_path / "downloads" / "Castlevania - Legacy of Darkness _USA_.zip"
    context = ImportContext(
        source_path=vanished,
        correlation_id=uuid4(),
        imported_via="automatic",
    )
    outcome = await run_import(context, session=async_session)

    assert outcome.success is True
    assert outcome.coalesced is True
    assert outcome.rejection_reason is None
    assert outcome.game_id == game.id

    # No bogus match:no_game history row, no spurious park entry.
    failure_rows = (
        await async_session.execute(
            select(ImportHistory).where(
                ImportHistory.correlation_id == str(context.correlation_id),
                ImportHistory.success.is_(False),
            )
        )
    ).scalars().all()
    assert failure_rows == []


@pytest.mark.asyncio
async def test_supersede_failed_siblings_sweeps_matching_failure(
    async_session: AsyncSession,
) -> None:
    """When qBit fires two events for one torrent with different
    native_ids, the first event lands as a bogus ``match:no_game``
    (no queue_entry pre-match) and the second succeeds. The
    success path's ``supersede_failed_siblings`` sweep deletes
    that misinformation row so the Activity feed stays truthful.

    Scope check: only matches rows with the same ``sha1``,
    ``success=False``, and within the recency window. Unrelated
    failures (different sha1, older) must survive."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from romarr.importer._outcome import supersede_failed_siblings

    same_sha = "a" * 40
    other_sha = "b" * 40
    now = datetime.now(UTC)

    # Three failure rows + the success-keeper.
    duplicate = ImportHistory(
        source_path="/downloads/Foo.zip",
        download_client_native_id="evil-twin",
        source_hash_sha1=same_sha,
        imported_via="automatic",
        success=False,
        coalesced=False,
        error_msg="match:no_game",
        correlation_id=str(uuid4()),
        started_at=now - timedelta(seconds=30),
    )
    unrelated = ImportHistory(
        source_path="/downloads/Bar.zip",
        source_hash_sha1=other_sha,  # different content → keep
        imported_via="automatic",
        success=False,
        coalesced=False,
        error_msg="match:no_game",
        correlation_id=str(uuid4()),
        started_at=now - timedelta(seconds=30),
    )
    too_old = ImportHistory(
        source_path="/downloads/Old.zip",
        source_hash_sha1=same_sha,
        imported_via="automatic",
        success=False,
        coalesced=False,
        error_msg="match:no_game",
        correlation_id=str(uuid4()),
        started_at=now - timedelta(hours=2),  # outside the 5-min window
    )
    keeper = ImportHistory(
        source_path="/downloads",
        source_hash_sha1=same_sha,
        imported_via="automatic",
        success=True,
        coalesced=False,
        correlation_id=str(uuid4()),
        started_at=now,
    )
    async_session.add_all([duplicate, unrelated, too_old, keeper])
    await async_session.flush()

    swept = await supersede_failed_siblings(
        session=async_session,
        sha1=same_sha,
        keep_history_id=keeper.id,
    )
    assert swept == 1  # only ``duplicate`` matches all three filters

    survivors = (
        await async_session.execute(select(ImportHistory))
    ).scalars().all()
    survivor_ids = {r.id for r in survivors}
    assert duplicate.id not in survivor_ids
    assert unrelated.id in survivor_ids
    assert too_old.id in survivor_ids
    assert keeper.id in survivor_ids


@pytest.mark.asyncio
async def test_run_import_late_queue_entry_resolution_avoids_bogus_no_game(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Dispatch-race: the search engine's auto-grab writes the
    ``QueueEntry.game_id`` in a separate session that hasn't
    committed yet when the watcher tick dispatches the import.
    The dispatcher reads ``pre_matched_game_id=None``, GAMEMATCH
    can't tie the opaque torrent filename to a game, and the
    orchestrator would otherwise park a bogus ``match:no_game``.

    By the time the orchestrator gets to the park step its own
    session view DOES see the freshly-committed ``queue_entry``
    row. Re-query and trust the late ``game_id`` — the auto-import
    branch's create-release fallback then completes the import
    cleanly."""
    from uuid import uuid4

    from romarr.api.models import QueueEntry
    from romarr.domain.models import Game, Platform
    from romarr.downloaders.models import DownloadClient

    # ROM whose filename can't be fuzzy-matched to a game
    # (mimics qBit-style opaque torrent name).
    rom = tmp_path / "downloads" / "gwsmb35.bin"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(b"\x00" * 4096)

    platform = Platform(slug="snes-late", name="SNES", manufacturer="Nintendo")
    async_session.add(platform)
    await async_session.flush()
    game = Game(
        platform_id=platform.id,
        slug="super-mario-bros-late",
        title="Super Mario Bros.",
    )
    async_session.add(game)
    await async_session.flush()

    # Stand-in download client + queue_entry: the search-engine's
    # auto-grab landed the ``game_id`` here AFTER the dispatcher
    # peeked. The orchestrator's own session sees it.
    dc = DownloadClient(
        name="qbit-late", type="qbittorrent", host="x", port=1,
    )
    async_session.add(dc)
    await async_session.flush()
    async_session.add(
        QueueEntry(
            download_client_id=dc.id,
            download_client_native_id="late-race-hash",
            game_id=game.id,
            title="gwsmb35",
            state="downloading",
            progress=1.0,
        )
    )
    await async_session.flush()

    context = ImportContext(
        source_path=rom,
        correlation_id=uuid4(),
        imported_via="automatic",
        download_client_id=dc.id,
        download_client_native_id="late-race-hash",
        # CRITICAL: pre_matched_game_id is None — simulating the
        # dispatcher having raced ahead of the auto-grab's commit.
        pre_matched_game_id=None,
    )
    outcome = await run_import(context, session=async_session)

    # Late queue_entry lookup recovered the game_id → auto-import
    # ran via the create-release fallback → success, not parked.
    assert outcome.success is True
    assert outcome.game_id == game.id
    assert outcome.rejection_reason is None

    failure_rows = (
        await async_session.execute(
            select(ImportHistory).where(
                ImportHistory.correlation_id == str(context.correlation_id),
                ImportHistory.success.is_(False),
            )
        )
    ).scalars().all()
    assert failure_rows == []
