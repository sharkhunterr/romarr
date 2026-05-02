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
    )
    return outcome_from_failure_history(
        history=history,
        context=context,
        exception=exception,
        duration_ms=duration_ms,
    )


__all__ = [
    "make_failure_outcome",
    "map_exception_to_reason",
    "outcome_from_failure_history",
    "persist_failure_history",
]
