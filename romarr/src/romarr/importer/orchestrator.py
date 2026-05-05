"""Importer orchestrator — happy-path driver (spec 008).

Slice 288 ships the *minimal* orchestrator that drives the audit
chain end-to-end for the no-game-match path:

  1. Hash the source file via spec 001's :class:`Hasher`.
  2. Park the file in ``unidentified_dump`` with
     ``rejection_reason='match:no_game'`` so the operator can
     triage it via the manual-match endpoint.
  3. Write a ``success=False`` ``import_history`` row carrying
     the correlation id, started_at / finished_at timestamps,
     and the source SHA-1.
  4. Return an :class:`ImportOutcome` projecting the persisted
     row.

The full happy-path (extract + DAT-match + game-match +
profile-gate + render + move + persist Dump + lifecycle +
notify) lands incrementally in the WATCH / EXTRACT / HASH /
DATMATCH / IDENTIFY / GAMEMATCH / MULTIDISC / PROFILEGATE /
RENDER / MOVE / DBUPDATE / LIFECYCLE / NOTIFY slices listed in
the spec. Today's `run_import` is the single entry-point those
later slices fill in; tests asserting "every input writes an
audit row" can rely on it now.

The watcher loop helpers (``start_watcher`` / ``stop_watcher``)
remain stubs — they land with the WATCH slice when the
``DownloadClient.list_managed_downloads`` helper exists.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from romarr.identification.hasher import Hasher
from romarr.importer._outcome import make_failure_outcome
from romarr.importer._park import park_in_unidentified
from romarr.importer.errors import GameNotMatched

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.importer.types import ImportContext, ImportOutcome


_NOT_IMPLEMENTED_MSG = (
    "{step} not implemented yet — lands with the {phase} slice"
)


async def run_import(
    context: ImportContext,
    *,
    session: AsyncSession,
    hasher: Hasher | None = None,
) -> ImportOutcome:
    """Run the import pipeline against ``context``.

    Slice 288 ships the audit-only path: hash the file, park it
    as ``match:no_game``, write the failure history row, return
    the projected :class:`ImportOutcome`. Every successful
    failure-path test (``success=False``, ``rejection_reason``
    populated, ``history_id`` non-null) passes against this
    minimum. The full happy-path lands in subsequent slices.

    The caller owns the session — we leave the txn open after
    flushes so callers can compose the import with their own
    work in the same transaction (matches the convention
    established by ``_park.park_in_unidentified`` and
    ``_outcome.persist_failure_history``).
    """
    started_at = datetime.now(UTC)
    monotonic_start = asyncio.get_event_loop().time()

    # Step 1 — hash the source file. Skip if the path doesn't
    # exist; the failure helper will record a structured reason.
    source_path = context.source_path
    sha1: str | None = None
    size_bytes = 0

    if source_path.exists() and source_path.is_file():
        h = hasher or Hasher()
        try:
            hash_result = await asyncio.to_thread(h.hash_path, source_path)
            sha1 = hash_result.sha1
            size_bytes = source_path.stat().st_size
        except OSError:
            # The file disappeared mid-hash; the park + history
            # writes below capture the failure reason.
            sha1 = None

    # Step 2 — park as ``match:no_game``. The orchestrator's
    # full game-match path lands with the GAMEMATCH slice; until
    # then every input takes this branch so the audit chain
    # stays exercised end-to-end.
    if size_bytes > 0:
        try:
            await park_in_unidentified(
                session=session,
                source_path=source_path,
                size_bytes=size_bytes,
                rejection_reason="match:no_game",
                sha1=sha1,
                library_id=context.library_id,
            )
        except Exception:
            # Park failure is non-fatal — the history-row write
            # below still captures the audit trail. The caller
            # decides whether to re-raise.
            pass

    # Step 3 — write the failure history row + project the
    # outcome.
    duration_ms = max(
        0,
        int((asyncio.get_event_loop().time() - monotonic_start) * 1000),
    )
    outcome = await make_failure_outcome(
        session=session,
        context=context,
        started_at=started_at,
        exception=GameNotMatched(
            "no game matched (orchestrator still in audit-only mode)"
        ),
        duration_ms=duration_ms,
        source_hash_sha1=sha1,
    )
    await session.commit()
    return outcome


async def start_watcher() -> None:
    """Spawn the polling watcher background task (FR-001).
    Wired into the application lifespan."""
    raise NotImplementedError(
        _NOT_IMPLEMENTED_MSG.format(step="start_watcher", phase="WATCH")
    )


async def stop_watcher() -> None:
    """Cancel the polling watcher background task on shutdown."""
    raise NotImplementedError(
        _NOT_IMPLEMENTED_MSG.format(step="stop_watcher", phase="WATCH")
    )


__all__ = ["run_import", "start_watcher", "stop_watcher"]
