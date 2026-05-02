"""Tests for the failure-outcome helpers (slice 77).

Covers :func:`map_exception_to_reason` (pure mapping),
:func:`persist_failure_history` (DB write), and
:func:`make_failure_outcome` (the convenience composite).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.importer._outcome import (
    make_failure_outcome,
    map_exception_to_reason,
    outcome_from_failure_history,
    persist_failure_history,
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
