"""Outcome construction helpers (slice 77).

The orchestrator's failure-handling block needs to:

  1. Map an in-flight exception to a structured
     :class:`RejectionReason` so the operator gets a typed
     ``import_history.error_msg`` rather than a stack trace.
  2. Persist an ``import_history`` row (success=False, no
     dest_path, no dump_id) carrying the rejection code +
     correlation id + duration.
  3. Project the persisted row into an :class:`ImportOutcome`
     so callers see a uniform shape regardless of how the
     pipeline failed.

This module provides the building blocks. The orchestrator
wraps every step in a try/except that funnels through
:func:`make_failure_outcome`. Tests cover the mapping +
persistence in isolation so the orchestrator's integration
slice doesn't have to re-test them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from romarr.importer.errors import (
    ExtractError,
    GameNotMatched,
    LockTimeout,
    MoveError,
    ProfileRejected,
)
from romarr.importer.models import ImportHistory
from romarr.importer.types import ImportContext, ImportOutcome, RejectionReason

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def map_exception_to_reason(exc: BaseException) -> RejectionReason | None:
    """Project an in-flight pipeline exception onto the structured
    :class:`RejectionReason` enum. Returns ``None`` for unmapped
    exceptions — the caller falls back to ``error_msg`` carrying
    the plain string.

    The mapping honors the documented prefix convention
    (``extract:*`` / ``move:*`` / ``profile:*`` / ``lock:*`` /
    ``match:*``). Sub-typed errors carry their own
    ``rejection_reason`` attribute we trust.
    """
    if isinstance(exc, ExtractError):
        return _coerce(exc.rejection_reason)
    if isinstance(exc, MoveError):
        return _coerce(exc.rejection_reason)
    if isinstance(exc, ProfileRejected):
        return _coerce(exc.rejection_reason)
    if isinstance(exc, GameNotMatched):
        return RejectionReason.NO_GAME_MATCH
    if isinstance(exc, LockTimeout):
        return RejectionReason.LOCK_TIMEOUT
    return None


def _coerce(raw: str) -> RejectionReason | None:
    """Convert the string carried on the exception to a
    :class:`RejectionReason`. Unknown strings return ``None`` so
    the orchestrator falls through to ``error_msg`` rather than
    silently masking a typo."""
    try:
        return RejectionReason(raw)
    except ValueError:
        return None


async def persist_failure_history(
    *,
    session: AsyncSession,
    context: ImportContext,
    started_at: datetime,
    exception: BaseException,
    duration_ms: int,
    source_hash_sha1: str | None = None,
    size_bytes: int | None = None,
) -> ImportHistory:
    """Insert a ``success=False`` row, return the persisted ORM
    object so the caller can read its ``id``.

    Caller is responsible for committing — we leave the txn open
    so the orchestrator can compose the failure-write with the
    same-transaction ``unidentified_dump`` parking when the
    failure path warrants it.
    """
    reason = map_exception_to_reason(exception)
    error_msg = reason.value if reason else f"{type(exception).__name__}: {exception}"

    row = ImportHistory(
        source_path=str(context.source_path),
        dest_path=None,
        download_client_id=context.download_client_id,
        download_client_native_id=context.download_client_native_id,
        game_id=None,
        release_id=None,
        dump_id=None,
        source_hash_sha1=source_hash_sha1,
        confidence=None,
        imported_via=context.imported_via,
        success=False,
        coalesced=False,
        warning=None,
        error_msg=error_msg,
        imported_by=context.imported_by,
        correlation_id=str(context.correlation_id),
        started_at=started_at,
        finished_at=datetime.now(UTC),
        duration_ms=duration_ms,
        size_bytes=size_bytes,
    )
    session.add(row)
    await session.flush()  # populates row.id
    return row


def outcome_from_failure_history(
    *,
    history: ImportHistory,
    context: ImportContext,
    exception: BaseException,
    duration_ms: int,
) -> ImportOutcome:
    """Project a freshly-persisted failure :class:`ImportHistory`
    into the :class:`ImportOutcome` shape callers consume."""
    reason = map_exception_to_reason(exception)
    return ImportOutcome(
        success=False,
        coalesced=False,
        dest_path=None,
        dump_id=None,
        release_id=None,
        game_id=None,
        confidence=None,
        warning=None,
        error_msg=history.error_msg,
        rejection_reason=reason,
        history_id=history.id,
        correlation_id=context.correlation_id,
        duration_ms=duration_ms,
    )


async def make_failure_outcome(
    *,
    session: AsyncSession,
    context: ImportContext,
    started_at: datetime,
    exception: BaseException,
    duration_ms: int,
    source_hash_sha1: str | None = None,
    size_bytes: int | None = None,
) -> ImportOutcome:
    """Convenience: persist + project in one call.

    Most failure-path call sites just want "turn this exception
    into a recorded ImportOutcome and move on". This helper
    composes :func:`persist_failure_history` and
    :func:`outcome_from_failure_history` so callers don't repeat
    the two-step dance.
    """
    history = await persist_failure_history(
        session=session,
        context=context,
        started_at=started_at,
        exception=exception,
        duration_ms=duration_ms,
        source_hash_sha1=source_hash_sha1,
        size_bytes=size_bytes,
    )
    return outcome_from_failure_history(
        history=history,
        context=context,
        exception=exception,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Success path — symmetric with the failure helpers above. The
# orchestrator records every successful import (including coalesced
# no-ops) so the audit trail stays complete (FR-031).


async def persist_success_history(
    *,
    session: AsyncSession,
    context: ImportContext,
    started_at: datetime,
    duration_ms: int,
    dest_path: str,
    game_id: int,
    release_id: int,
    dump_id: int,
    source_hash_sha1: str,
    confidence: float | None = None,
    coalesced: bool = False,
    warning: str | None = None,
    size_bytes: int | None = None,
) -> ImportHistory:
    """Insert a ``success=True`` row, return the persisted ORM
    object so the caller can read its ``id``.

    Caller is responsible for committing — the orchestrator
    composes the success-write with the same-transaction
    Dump / Release status updates from the DBUPDATE step.

    `coalesced=True` records "this was a re-import of a file
    we already had" — the row carries the same dest_path /
    dump_id as the original but the operator can audit the
    re-attempt.
    """
    row = ImportHistory(
        source_path=str(context.source_path),
        dest_path=dest_path,
        download_client_id=context.download_client_id,
        download_client_native_id=context.download_client_native_id,
        game_id=game_id,
        release_id=release_id,
        dump_id=dump_id,
        source_hash_sha1=source_hash_sha1,
        confidence=confidence,
        imported_via=context.imported_via,
        success=True,
        coalesced=coalesced,
        warning=warning,
        error_msg=None,
        imported_by=context.imported_by,
        correlation_id=str(context.correlation_id),
        started_at=started_at,
        finished_at=datetime.now(UTC),
        duration_ms=duration_ms,
        size_bytes=size_bytes,
    )
    session.add(row)
    await session.flush()  # populates row.id
    return row


def outcome_from_success_history(
    *,
    history: ImportHistory,
    context: ImportContext,
    duration_ms: int,
) -> ImportOutcome:
    """Project a freshly-persisted success :class:`ImportHistory`
    into the :class:`ImportOutcome` shape callers consume.

    Pure projection — no DB. The orchestrator pre-computes the
    duration once at the top of the success-path branch and
    reuses it for both the persistence and the projection so
    the two reports agree to the millisecond.
    """
    return ImportOutcome(
        success=True,
        coalesced=history.coalesced,
        dest_path=history.dest_path,  # type: ignore[arg-type]  # str -> Path coerced by Pydantic
        dump_id=history.dump_id,
        release_id=history.release_id,
        game_id=history.game_id,
        confidence=(
            float(history.confidence) if history.confidence is not None else None
        ),
        warning=history.warning,
        error_msg=None,
        rejection_reason=None,
        history_id=history.id,
        correlation_id=context.correlation_id,
        duration_ms=duration_ms,
    )


async def make_success_outcome(
    *,
    session: AsyncSession,
    context: ImportContext,
    started_at: datetime,
    duration_ms: int,
    dest_path: str,
    game_id: int,
    release_id: int,
    dump_id: int,
    source_hash_sha1: str,
    confidence: float | None = None,
    coalesced: bool = False,
    warning: str | None = None,
    size_bytes: int | None = None,
) -> ImportOutcome:
    """Convenience: persist + project in one call. Mirrors
    :func:`make_failure_outcome` so the orchestrator's two
    branches (success / failure) read symmetrically."""
    history = await persist_success_history(
        session=session,
        context=context,
        started_at=started_at,
        duration_ms=duration_ms,
        dest_path=dest_path,
        game_id=game_id,
        release_id=release_id,
        dump_id=dump_id,
        source_hash_sha1=source_hash_sha1,
        confidence=confidence,
        coalesced=coalesced,
        warning=warning,
        size_bytes=size_bytes,
    )
    return outcome_from_success_history(
        history=history,
        context=context,
        duration_ms=duration_ms,
    )


async def supersede_failed_siblings(
    *,
    session: AsyncSession,
    sha1: str,
    keep_history_id: int,
    within_seconds: int = 300,
) -> int:
    """Delete recent failed import_history rows whose ``sha1``
    matches the just-succeeded one.

    Returns the count of deleted rows.

    Why: qBit (and other clients) occasionally fire TWO events
    for one logical download with DIFFERENT ``native_id`` values
    (the .torrent's info-hash and a category/wrapper id). The
    dispatcher routes each event independently — the one whose
    native_id matches a ``queue_entry.game_id`` succeeds, the
    other doesn't have a pre-match and parks as
    ``match:no_game``. The failure row is misinformation: the
    content WAS imported successfully (the surviving sibling),
    just under a different dispatch identity. Once a successful
    sibling lands, the failure row is pure clutter on the
    Activity feed — sweep it.

    Scope:
      * ``success = False`` (only the noise)
      * same ``sha1`` (proves it's the same content)
      * within ``within_seconds`` of the success
      * NOT the keeper (``id != keep_history_id``) — defensive
        against re-running this on the just-written success
    """
    from datetime import timedelta
    from sqlalchemy import delete

    cutoff = datetime.now(UTC) - timedelta(seconds=within_seconds)
    result = await session.execute(
        delete(ImportHistory).where(
            ImportHistory.id != keep_history_id,
            ImportHistory.success.is_(False),
            ImportHistory.source_hash_sha1 == sha1.lower(),
            ImportHistory.started_at >= cutoff,
        )
    )
    return result.rowcount or 0


__all__ = [
    "make_failure_outcome",
    "make_success_outcome",
    "map_exception_to_reason",
    "outcome_from_failure_history",
    "outcome_from_success_history",
    "persist_failure_history",
    "persist_success_history",
    "supersede_failed_siblings",
]
