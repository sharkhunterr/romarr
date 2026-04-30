"""Stuck-grab retry state machine (Phase 8).

Pure-function transitions over a :class:`QueueEntry` value object,
plus the constants the future scheduler ticks at:

  * ``RETRY_INTERVAL`` — 5 minutes between retry attempts.
  * ``FAILURE_CEILING`` — 1 hour from the initial failure; past that
    the entry transitions to :class:`QueueEntryState.FAILED` and a
    notification event is requested.

The actual ``queue_entry`` table is owned by the API spec; this
module ships only the logic. Persistence + scheduling glue (the
5-minute APScheduler job) lives in the future Tasks/Scheduler spec.

Why pure functions and not a class? The retry policy MUST be unit
testable without a database, without the scheduler, and without
network. Splitting "decide" (here) from "act" (the orchestrator)
keeps the policy table-driven and trivial to reason about.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from romarr.downloaders.errors import AuthError, VersionError

RETRY_INTERVAL = timedelta(minutes=5)
"""Cadence between retry attempts on a STUCK entry (FR-022)."""

FAILURE_CEILING = timedelta(hours=1)
"""Hard ceiling — after this much time stuck, mark FAILED (FR-022 / SC-007)."""


class QueueEntryState(StrEnum):
    """Lifecycle of one queue entry as the retry layer sees it.

    The future ``queue_entry`` table will persist this verbatim;
    additional implementation-internal states (e.g., post-import
    bookkeeping) belong on the importer side, not here.
    """

    PENDING = "pending"
    DOWNLOADING = "downloading"
    STUCK = "stuck"            # transient client outage; in retry rotation
    FAILED = "failed"          # exceeded the 1-hour ceiling or non-transient
    COMPLETED = "completed"


_TERMINAL = (QueueEntryState.FAILED, QueueEntryState.COMPLETED)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class QueueEntry(_Base):
    """One persisted queue entry as seen by the retry decider.

    All fields are read-only inputs; transitions return a fresh
    :class:`QueueEntryUpdate` rather than mutating the entry in
    place. That makes the state machine trivially deterministic.
    """

    id: int
    client_id: int
    release_id: int
    state: QueueEntryState
    attempt_count: int = Field(ge=0)
    first_stuck_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_error: str | None = None

    @model_validator(mode="after")
    def _stuck_invariants(self) -> Self:
        if self.state is QueueEntryState.STUCK:
            if self.first_stuck_at is None:
                raise ValueError("STUCK entries must have first_stuck_at set")
            if self.last_attempt_at is None:
                raise ValueError("STUCK entries must have last_attempt_at set")
        return self


class QueueEntryUpdate(_Base):
    """An in-memory update the orchestrator should persist.

    The orchestrator (a future scheduler task) commits the update to
    the ``queue_entry`` table and optionally fans the
    notification event out through the spec 011 notification spine.
    """

    id: int
    state: QueueEntryState
    attempt_count: int
    first_stuck_at: datetime | None
    last_attempt_at: datetime
    last_error: str | None
    client_native_id: str | None = None
    notify: bool = False
    """True iff this transition deserves an OnGrab/OnFail notification."""


# ---------------------------------------------------------------------------
# Initial attempt (called once when the grab fires)
# ---------------------------------------------------------------------------


def _is_non_transient(error: BaseException) -> bool:
    """Errors that should never be retried — fail immediately.

    AuthError + VersionError are configuration problems, not flakes.
    """
    return isinstance(error, AuthError | VersionError)


def record_initial_success(
    *,
    entry_id: int,
    client_id: int,
    release_id: int,
    now: datetime,
    client_native_id: str,
) -> QueueEntryUpdate:
    """The first attempt succeeded — entry is now downloading."""
    return QueueEntryUpdate(
        id=entry_id,
        state=QueueEntryState.DOWNLOADING,
        attempt_count=1,
        first_stuck_at=None,
        last_attempt_at=now,
        last_error=None,
        client_native_id=client_native_id,
        notify=False,
    )


def record_initial_failure(
    *,
    entry_id: int,
    client_id: int,
    release_id: int,
    now: datetime,
    error: BaseException,
) -> QueueEntryUpdate:
    """The first attempt failed.

    Non-transient errors (auth, version) → FAILED + notify.
    Transient errors → STUCK; the scheduler will retry every 5 min.
    """
    state = QueueEntryState.FAILED if _is_non_transient(error) else QueueEntryState.STUCK
    notify = state is QueueEntryState.FAILED
    return QueueEntryUpdate(
        id=entry_id,
        state=state,
        attempt_count=1,
        first_stuck_at=now if state is QueueEntryState.STUCK else None,
        last_attempt_at=now,
        last_error=str(error),
        notify=notify,
    )


# ---------------------------------------------------------------------------
# Retry transitions (called by the scheduler tick on STUCK entries)
# ---------------------------------------------------------------------------


def is_due_for_retry(entry: QueueEntry, *, now: datetime) -> bool:
    """True iff at least RETRY_INTERVAL has elapsed since the last attempt."""
    if entry.last_attempt_at is None:
        return True
    return (now - entry.last_attempt_at) >= RETRY_INTERVAL


def is_over_ceiling(entry: QueueEntry, *, now: datetime) -> bool:
    """True iff the entry has been STUCK for at least FAILURE_CEILING."""
    if entry.first_stuck_at is None:
        return False
    return (now - entry.first_stuck_at) >= FAILURE_CEILING


def _ensure_active(entry: QueueEntry) -> None:
    if entry.state in _TERMINAL:
        raise ValueError(
            f"queue entry {entry.id} is already in terminal state {entry.state}"
        )


def record_attempt_success(
    entry: QueueEntry,
    *,
    now: datetime,
    client_native_id: str,
) -> QueueEntryUpdate:
    """A retry succeeded.

    Transitions to DOWNLOADING and resets the attempt counter so a
    later transient failure starts a fresh 1-hour window (T055).
    """
    _ensure_active(entry)
    return QueueEntryUpdate(
        id=entry.id,
        state=QueueEntryState.DOWNLOADING,
        attempt_count=0,
        first_stuck_at=None,
        last_attempt_at=now,
        last_error=None,
        client_native_id=client_native_id,
        notify=False,
    )


def record_attempt_failure(
    entry: QueueEntry,
    *,
    now: datetime,
    error: BaseException,
) -> QueueEntryUpdate:
    """A retry failed.

    Past the 1-hour ceiling → FAILED + notify (T054).
    Non-transient error → FAILED + notify regardless of clock.
    Otherwise → STUCK with attempt_count + 1 (T055).
    """
    _ensure_active(entry)
    if _is_non_transient(error) or is_over_ceiling(entry, now=now):
        return QueueEntryUpdate(
            id=entry.id,
            state=QueueEntryState.FAILED,
            attempt_count=entry.attempt_count + 1,
            first_stuck_at=entry.first_stuck_at,
            last_attempt_at=now,
            last_error=str(error),
            notify=True,
        )
    return QueueEntryUpdate(
        id=entry.id,
        state=QueueEntryState.STUCK,
        attempt_count=entry.attempt_count + 1,
        first_stuck_at=entry.first_stuck_at,
        last_attempt_at=now,
        last_error=str(error),
        notify=False,
    )


__all__ = [
    "FAILURE_CEILING",
    "RETRY_INTERVAL",
    "QueueEntry",
    "QueueEntryState",
    "QueueEntryUpdate",
    "is_due_for_retry",
    "is_over_ceiling",
    "record_attempt_failure",
    "record_attempt_success",
    "record_initial_failure",
    "record_initial_success",
]
