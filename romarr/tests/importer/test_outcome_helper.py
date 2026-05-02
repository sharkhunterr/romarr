"""Tests for the outcome helpers (slices 77 + 78).

Covers :func:`map_exception_to_reason` (pure mapping),
:func:`persist_failure_history` + :func:`make_failure_outcome`
(failure-path DB), :func:`persist_success_history` +
:func:`make_success_outcome` (success-path DB).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Dump, Game, Platform, Release
from romarr.importer._outcome import (
    make_failure_outcome,
    make_success_outcome,
    map_exception_to_reason,
    outcome_from_failure_history,
    outcome_from_success_history,
    persist_failure_history,
    persist_success_history,
)
from romarr.importer.errors import (
    ExtractError,
    GameNotMatched,
    LockTimeout,
    MoveError,
    ProfileRejected,
)
from romarr.importer.models import ImportHistory
from romarr.importer.types import ImportContext, RejectionReason


# ---------------------------------------------------------------------------
# map_exception_to_reason


class TestMapExceptionToReason:
    """Pure mapping — no DB. Cover every documented exception
    type plus the unmapped fallback."""

    def test_extract_error_passes_through_known_reason(self) -> None:
        exc = ExtractError(
            "bomb detected",
            rejection_reason=RejectionReason.EXTRACT_BOMB_DETECTED.value,
        )
        assert map_exception_to_reason(exc) is RejectionReason.EXTRACT_BOMB_DETECTED

    def test_move_error_passes_through_known_reason(self) -> None:
        exc = MoveError(
            "hash mismatch",
            rejection_reason=RejectionReason.MOVE_HASH_MISMATCH.value,
        )
        assert map_exception_to_reason(exc) is RejectionReason.MOVE_HASH_MISMATCH

    def test_profile_rejected_passes_through(self) -> None:
        exc = ProfileRejected(
            "language not allowed",
            rejection_reason=RejectionReason.PROFILE_LANGUAGE_REJECT.value,
        )
        assert (
            map_exception_to_reason(exc) is RejectionReason.PROFILE_LANGUAGE_REJECT
        )

    def test_game_not_matched_maps_to_no_game(self) -> None:
        assert (
            map_exception_to_reason(GameNotMatched("no candidates"))
            is RejectionReason.NO_GAME_MATCH
        )

    def test_lock_timeout_maps_to_lock_timeout(self) -> None:
        assert (
            map_exception_to_reason(LockTimeout("timed out after 60s"))
            is RejectionReason.LOCK_TIMEOUT
        )

    def test_unknown_extract_subreason_falls_through_to_none(self) -> None:
        # An ExtractError carrying a string outside the enum: the
        # mapper returns None so the orchestrator falls back to
        # ``error_msg`` rather than silently masking a typo.
        exc = ExtractError("typo", rejection_reason="extract:made-up")
        assert map_exception_to_reason(exc) is None

    def test_unrelated_exception_returns_none(self) -> None:
        assert map_exception_to_reason(RuntimeError("bug")) is None

    def test_value_error_returns_none(self) -> None:
        assert map_exception_to_reason(ValueError("oops")) is None


# ---------------------------------------------------------------------------
# persist_failure_history + outcome_from_failure_history (DB)


def _ctx(tmp_path) -> ImportContext:
    source = tmp_path / "rom.zip"
    source.write_bytes(b"x")
    return ImportContext(
        source_path=source,
        correlation_id=uuid4(),
        imported_via="manual",
        imported_by="alice",
        # No download_client_id — the FK target isn't seeded in
        # the importer test DB. The native_id stays so we exercise
        # that field independently of the FK.
        download_client_native_id="hash-7",
    )


@pytest.mark.asyncio
async def test_persist_failure_history_writes_known_reason(
    async_session: AsyncSession, tmp_path
) -> None:
    ctx = _ctx(tmp_path)
    started = datetime.now(UTC)
    exc = ExtractError(
        "bomb",
        rejection_reason=RejectionReason.EXTRACT_BOMB_DETECTED.value,
    )

    row = await persist_failure_history(
        session=async_session,
        context=ctx,
        started_at=started,
        exception=exc,
        duration_ms=1234,
        source_hash_sha1="b" * 40,
    )
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == row.id)
        )
    ).scalar_one()
    assert fetched.success is False
    assert fetched.coalesced is False
    assert fetched.dest_path is None
    assert fetched.dump_id is None
    assert fetched.error_msg == RejectionReason.EXTRACT_BOMB_DETECTED.value
    assert fetched.imported_via == "manual"
    assert fetched.imported_by == "alice"
    assert fetched.download_client_id is None
    assert fetched.download_client_native_id == "hash-7"
    assert fetched.source_hash_sha1 == "b" * 40
    assert fetched.duration_ms == 1234
    assert fetched.correlation_id == str(ctx.correlation_id)
    assert fetched.started_at.replace(tzinfo=UTC) == started.replace(tzinfo=UTC)
    assert fetched.finished_at is not None


@pytest.mark.asyncio
async def test_persist_failure_history_falls_back_to_error_str(
    async_session: AsyncSession, tmp_path
) -> None:
    """An unmapped exception goes into ``error_msg`` as the
    formatted ``Type: message`` string so the operator still
    sees something actionable."""
    ctx = _ctx(tmp_path)
    started = datetime.now(UTC)
    exc = RuntimeError("permission denied somewhere")

    row = await persist_failure_history(
        session=async_session,
        context=ctx,
        started_at=started,
        exception=exc,
        duration_ms=10,
    )
    await async_session.commit()

    assert row.error_msg == "RuntimeError: permission denied somewhere"


def test_outcome_from_failure_history_projects_history_row() -> None:
    """Projection is pure — no DB, no async — once the history
    row is in hand."""
    ctx = ImportContext(
        source_path="/downloads/x.zip",  # type: ignore[arg-type]
        correlation_id=uuid4(),
        imported_via="manual",
    )
    history = ImportHistory(
        id=99,
        source_path="/downloads/x.zip",
        imported_via="manual",
        success=False,
        correlation_id=str(ctx.correlation_id),
        started_at=datetime.now(UTC),
        error_msg=RejectionReason.NO_GAME_MATCH.value,
    )
    outcome = outcome_from_failure_history(
        history=history,
        context=ctx,
        exception=GameNotMatched("none"),
        duration_ms=42,
    )

    assert outcome.success is False
    assert outcome.history_id == 99
    assert outcome.rejection_reason is RejectionReason.NO_GAME_MATCH
    assert outcome.error_msg == RejectionReason.NO_GAME_MATCH.value
    assert outcome.duration_ms == 42
    assert outcome.correlation_id == ctx.correlation_id
    assert outcome.dest_path is None
    assert outcome.dump_id is None


@pytest.mark.asyncio
async def test_make_failure_outcome_composes_persist_and_project(
    async_session: AsyncSession, tmp_path
) -> None:
    """Convenience wrapper produces an Outcome whose history_id
    matches a row that exists in the DB after the call."""
    ctx = _ctx(tmp_path)
    started = datetime.now(UTC)
    exc = LockTimeout("60s elapsed")

    outcome = await make_failure_outcome(
        session=async_session,
        context=ctx,
        started_at=started,
        exception=exc,
        duration_ms=60_000,
    )
    await async_session.commit()

    assert outcome.success is False
    assert outcome.rejection_reason is RejectionReason.LOCK_TIMEOUT
    assert outcome.duration_ms == 60_000
    assert outcome.history_id > 0

    fetched = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == outcome.history_id)
        )
    ).scalar_one()
    assert fetched.success is False
    assert fetched.error_msg == RejectionReason.LOCK_TIMEOUT.value
    assert fetched.imported_via == "manual"


# ---------------------------------------------------------------------------
# Success path — needs real Game / Release / Dump rows for the FKs
# (ON DELETE SET NULL means the FKs are NULLable but they're still
# checked when non-null at insert time).


async def _seed_success_chain(
    session: AsyncSession,
) -> tuple[int, int, int]:
    """Seed Platform → Game → Release → Dump and return
    (game_id, release_id, dump_id)."""
    platform = Platform(slug="megadrive", name="Mega Drive")
    session.add(platform)
    await session.flush()
    game = Game(
        platform_id=platform.id,
        slug="sonic-the-hedgehog",
        title="Sonic the Hedgehog",
    )
    session.add(game)
    await session.flush()
    release = Release(
        game_id=game.id,
        name="Sonic the Hedgehog (USA)",
    )
    session.add(release)
    await session.flush()
    dump = Dump(
        release_id=release.id,
        path=f"/library/megadrive/Sonic_{uuid4().hex}.md",
        original_filename="Sonic the Hedgehog (USA).md",
        size_bytes=524288,
        format="md",
        crc32="d3578bf6",
        md5="d" * 32,
        sha1="a" * 40,
    )
    session.add(dump)
    await session.flush()
    return game.id, release.id, dump.id


@pytest.mark.asyncio
async def test_persist_success_history_round_trip(
    async_session: AsyncSession, tmp_path
) -> None:
    ctx = _ctx(tmp_path)
    started = datetime.now(UTC)
    game_id, release_id, dump_id = await _seed_success_chain(async_session)

    row = await persist_success_history(
        session=async_session,
        context=ctx,
        started_at=started,
        duration_ms=4567,
        dest_path="/library/megadrive/Sonic.md",
        game_id=game_id,
        release_id=release_id,
        dump_id=dump_id,
        source_hash_sha1="c" * 40,
        confidence=0.92,
        coalesced=False,
    )
    await async_session.commit()

    fetched = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == row.id)
        )
    ).scalar_one()
    assert fetched.success is True
    assert fetched.coalesced is False
    assert fetched.dest_path == "/library/megadrive/Sonic.md"
    assert fetched.game_id == game_id
    assert fetched.release_id == release_id
    assert fetched.dump_id == dump_id
    assert fetched.error_msg is None
    assert fetched.warning is None
    assert float(fetched.confidence) == pytest.approx(0.92)
    assert fetched.source_hash_sha1 == "c" * 40
    assert fetched.duration_ms == 4567


@pytest.mark.asyncio
async def test_persist_success_history_coalesced_marker(
    async_session: AsyncSession, tmp_path
) -> None:
    """Re-import of an already-known file: success=True,
    coalesced=True, audit row carries the same destination as
    the original."""
    ctx = _ctx(tmp_path)
    started = datetime.now(UTC)
    game_id, release_id, dump_id = await _seed_success_chain(async_session)

    row = await persist_success_history(
        session=async_session,
        context=ctx,
        started_at=started,
        duration_ms=120,
        dest_path="/library/megadrive/Sonic.md",
        game_id=game_id,
        release_id=release_id,
        dump_id=dump_id,
        source_hash_sha1="c" * 40,
        coalesced=True,
        warning="re-import of identical file",
    )
    await async_session.commit()

    assert row.coalesced is True
    assert row.warning == "re-import of identical file"
    assert row.success is True


def test_outcome_from_success_history_is_pure_projection() -> None:
    """No DB call — just project a freshly-built history row."""
    ctx = ImportContext(
        source_path="/downloads/x.zip",  # type: ignore[arg-type]
        correlation_id=uuid4(),
        imported_via="webhook",
    )
    history = ImportHistory(
        id=42,
        source_path="/downloads/x.zip",
        dest_path="/library/megadrive/X.md",
        imported_via="webhook",
        success=True,
        coalesced=False,
        correlation_id=str(ctx.correlation_id),
        started_at=datetime.now(UTC),
        game_id=10,
        release_id=11,
        dump_id=12,
        confidence=0.88,
    )
    outcome = outcome_from_success_history(
        history=history, context=ctx, duration_ms=999
    )
    assert outcome.success is True
    assert outcome.history_id == 42
    assert outcome.game_id == 10
    assert outcome.release_id == 11
    assert outcome.dump_id == 12
    assert outcome.dest_path is not None
    assert str(outcome.dest_path) == "/library/megadrive/X.md"
    assert outcome.confidence == pytest.approx(0.88)
    assert outcome.duration_ms == 999
    assert outcome.error_msg is None
    assert outcome.rejection_reason is None


@pytest.mark.asyncio
async def test_make_success_outcome_composes_persist_and_project(
    async_session: AsyncSession, tmp_path
) -> None:
    """The composite mirrors `make_failure_outcome`'s shape."""
    ctx = _ctx(tmp_path)
    started = datetime.now(UTC)
    game_id, release_id, dump_id = await _seed_success_chain(async_session)

    outcome = await make_success_outcome(
        session=async_session,
        context=ctx,
        started_at=started,
        duration_ms=2000,
        dest_path="/library/megadrive/Sonic.md",
        game_id=game_id,
        release_id=release_id,
        dump_id=dump_id,
        source_hash_sha1="c" * 40,
        confidence=0.96,
    )
    await async_session.commit()

    assert outcome.success is True
    assert outcome.history_id > 0
    assert outcome.duration_ms == 2000

    fetched = (
        await async_session.execute(
            select(ImportHistory).where(ImportHistory.id == outcome.history_id)
        )
    ).scalar_one()
    assert fetched.success is True
    assert fetched.dest_path == "/library/megadrive/Sonic.md"
    assert float(fetched.confidence) == pytest.approx(0.96)
