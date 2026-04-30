"""Stuck-grab retry state machine tests (T052-T055)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from romarr.downloaders.errors import AuthError
from romarr.downloaders.errors import ConnectionError as DownloaderConnError
from romarr.downloaders.retry import (
    FAILURE_CEILING,
    RETRY_INTERVAL,
    QueueEntry,
    QueueEntryState,
    is_due_for_retry,
    is_over_ceiling,
    record_attempt_failure,
    record_attempt_success,
    record_initial_failure,
    record_initial_success,
)

_T0 = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)


def _stuck_entry(
    *,
    attempt_count: int = 1,
    first_stuck_at: datetime | None = None,
    last_attempt_at: datetime | None = None,
) -> QueueEntry:
    return QueueEntry(
        id=1,
        client_id=1,
        release_id=42,
        state=QueueEntryState.STUCK,
        attempt_count=attempt_count,
        first_stuck_at=first_stuck_at or _T0,
        last_attempt_at=last_attempt_at or _T0,
        last_error="connection refused",
    )


# ---------------------------------------------------------------------------
# T052 — initial ConnectionError → STUCK
# ---------------------------------------------------------------------------


def test_initial_connection_error_marks_stuck() -> None:
    update = record_initial_failure(
        entry_id=1,
        client_id=1,
        release_id=42,
        now=_T0,
        error=DownloaderConnError("connection refused"),
    )
    assert update.state is QueueEntryState.STUCK
    assert update.attempt_count == 1
    assert update.first_stuck_at == _T0
    assert update.last_attempt_at == _T0
    assert update.last_error == "connection refused"
    assert update.notify is False  # initial stuck doesn't fire a notification


def test_initial_auth_error_marks_failed_immediately() -> None:
    """Auth errors are non-transient — bail out, don't retry."""
    update = record_initial_failure(
        entry_id=1,
        client_id=1,
        release_id=42,
        now=_T0,
        error=AuthError("bad credentials"),
    )
    assert update.state is QueueEntryState.FAILED
    assert update.notify is True


def test_initial_success_marks_downloading() -> None:
    update = record_initial_success(
        entry_id=1,
        client_id=1,
        release_id=42,
        now=_T0,
        client_native_id="abc",
    )
    assert update.state is QueueEntryState.DOWNLOADING
    assert update.attempt_count == 1
    assert update.client_native_id == "abc"


# ---------------------------------------------------------------------------
# T053 — retry after 5 minutes
# ---------------------------------------------------------------------------


def test_due_for_retry_at_5_minutes() -> None:
    entry = _stuck_entry(last_attempt_at=_T0)
    assert is_due_for_retry(entry, now=_T0 + RETRY_INTERVAL) is True


def test_not_due_for_retry_before_5_minutes() -> None:
    entry = _stuck_entry(last_attempt_at=_T0)
    assert is_due_for_retry(entry, now=_T0 + timedelta(minutes=4, seconds=59)) is False


def test_retry_success_transitions_to_downloading() -> None:
    """T053: a successful retry transitions the stuck entry to DOWNLOADING."""
    entry = _stuck_entry(last_attempt_at=_T0)
    later = _T0 + RETRY_INTERVAL
    update = record_attempt_success(entry, now=later, client_native_id="hash-abc")
    assert update.state is QueueEntryState.DOWNLOADING
    assert update.last_attempt_at == later
    assert update.client_native_id == "hash-abc"


# ---------------------------------------------------------------------------
# T054 — failure after 1 hour
# ---------------------------------------------------------------------------


def test_is_over_ceiling_at_one_hour() -> None:
    entry = _stuck_entry(first_stuck_at=_T0)
    assert is_over_ceiling(entry, now=_T0 + FAILURE_CEILING) is True


def test_is_not_over_ceiling_before_one_hour() -> None:
    entry = _stuck_entry(first_stuck_at=_T0)
    assert is_over_ceiling(entry, now=_T0 + timedelta(minutes=59)) is False


def test_failure_after_one_hour_emits_notification() -> None:
    """T054: 13 failed retries x 5min >= 65min -> state transitions to FAILED
    and notify is set so the operator is told once.
    """
    entry = _stuck_entry(
        attempt_count=12,
        first_stuck_at=_T0,
        last_attempt_at=_T0 + timedelta(minutes=60),
    )
    later = _T0 + timedelta(minutes=65)
    update = record_attempt_failure(
        entry,
        now=later,
        error=DownloaderConnError("still refused"),
    )
    assert update.state is QueueEntryState.FAILED
    assert update.notify is True
    assert update.attempt_count == 13


def test_repeated_failure_under_one_hour_stays_stuck() -> None:
    entry = _stuck_entry(first_stuck_at=_T0, last_attempt_at=_T0)
    later = _T0 + timedelta(minutes=10)
    update = record_attempt_failure(
        entry,
        now=later,
        error=DownloaderConnError("refused"),
    )
    assert update.state is QueueEntryState.STUCK
    assert update.notify is False
    assert update.attempt_count == 2
    assert update.last_attempt_at == later


# ---------------------------------------------------------------------------
# T055 — recovery resets attempts
# ---------------------------------------------------------------------------


def test_recovery_resets_attempt_count() -> None:
    """T055: after a successful retry, attempt_count → 0 (fresh window)."""
    entry = _stuck_entry(attempt_count=7, first_stuck_at=_T0)
    later = _T0 + RETRY_INTERVAL
    update = record_attempt_success(entry, now=later, client_native_id="hash-abc")
    assert update.attempt_count == 0
    assert update.first_stuck_at is None  # cleared on recovery


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_initial_failure_with_unknown_error_marks_stuck() -> None:
    """Unrecognised errors default to transient — operator can investigate."""
    update = record_initial_failure(
        entry_id=1,
        client_id=1,
        release_id=42,
        now=_T0,
        error=TimeoutError("timed out"),
    )
    assert update.state is QueueEntryState.STUCK


def test_record_attempt_failure_on_already_failed_is_noop() -> None:
    """Once an entry is FAILED, further outcomes don't change its state."""
    entry = QueueEntry(
        id=1,
        client_id=1,
        release_id=42,
        state=QueueEntryState.FAILED,
        attempt_count=13,
        first_stuck_at=_T0,
        last_attempt_at=_T0 + timedelta(minutes=60),
        last_error="too many",
    )
    with pytest.raises(ValueError, match="already in terminal state"):
        record_attempt_failure(
            entry, now=_T0 + timedelta(hours=2), error=DownloaderConnError("x")
        )
