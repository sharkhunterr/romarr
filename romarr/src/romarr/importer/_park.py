"""Park-in-`unidentified_dump` helper (slice 79).

The orchestrator parks a file into ``unidentified_dump`` when:

  * Identification can't pin a Game above the confidence
    threshold (FR-013, ``rejection_reason='match:no_game'``).
  * A destination collision is detected with a different SHA-1
    (CL003, ``rejection_reason='destination_collision'``).
  * Extraction fails on a parkable sub-reason (bomb, depth,
    bad-archive — CL004).
  * Any profile gate rejects an automatic-flow candidate
    (CL001 — content-correctness sub-reasons).

Parking is **idempotent on path**: a second park for the same
``source_path`` updates the existing row (bumps
``attempt_count``, refreshes ``last_attempt_at`` and
``rejection_reason``) instead of raising on the unique
constraint. This matches the documented retry semantics — the
operator can re-trigger an import for a parked file and see
the attempt count climb.

Caller is responsible for committing — we leave the txn open
so the orchestrator can compose the park with the
``import_history`` failure-row write inside the same
transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.domain.models import UnidentifiedDump

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession


async def park_in_unidentified(
    *,
    session: AsyncSession,
    source_path: Path,
    size_bytes: int,
    rejection_reason: str,
    crc32: str | None = None,
    md5: str | None = None,
    sha1: str | None = None,
    suggested_platform_id: int | None = None,
    suggested_game_id: int | None = None,
    library_id: int | None = None,
    last_error: str | None = None,
) -> UnidentifiedDump:
    """Insert or update an ``unidentified_dump`` row keyed on
    ``source_path``. Returns the persisted ORM object.

    Behaviour:

      * **First park** for this path: INSERT a new row,
        ``attempt_count = 1``, ``discovered_at = now()``.
      * **Re-park** for the same path: UPDATE the existing row,
        bump ``attempt_count``, refresh
        ``last_attempt_at`` and ``rejection_reason``. Hashes
        and other hints are refreshed when the caller passes
        non-``None`` values; we keep the previously-recorded
        value otherwise (operators value the first signal we
        had over a no-op recompute).

    The caller commits — the orchestrator wraps this with the
    ``import_history`` write so a crash between the two leaves
    no half-state.
    """
    path_str = str(source_path)
    now = datetime.now(UTC)

    existing = (
        await session.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.path == path_str)
        )
    ).scalar_one_or_none()

    if existing is None:
        row = UnidentifiedDump(
            path=path_str,
            size_bytes=size_bytes,
            discovered_at=now,
            crc32=crc32,
            md5=md5,
            sha1=sha1,
            attempt_count=1,
            last_attempt_at=now,
            last_error=last_error,
            suggested_platform_id=suggested_platform_id,
            suggested_game_id=suggested_game_id,
            library_id=library_id,
            rejection_reason=rejection_reason,
        )
        session.add(row)
        await session.flush()
        return row

    # Re-park — keep the original discovered_at, bump the
    # attempt counter, refresh whatever new info the caller
    # learned this round.
    existing.attempt_count = (existing.attempt_count or 0) + 1
    existing.last_attempt_at = now
    existing.rejection_reason = rejection_reason
    if last_error is not None:
        existing.last_error = last_error
    if crc32 is not None:
        existing.crc32 = crc32
    if md5 is not None:
        existing.md5 = md5
    if sha1 is not None:
        existing.sha1 = sha1
    if suggested_platform_id is not None:
        existing.suggested_platform_id = suggested_platform_id
    if suggested_game_id is not None:
        existing.suggested_game_id = suggested_game_id
    if library_id is not None:
        existing.library_id = library_id
    # size_bytes is rewritten — the file may have been
    # repackaged between attempts.
    existing.size_bytes = size_bytes
    await session.flush()
    return existing


__all__ = ["park_in_unidentified"]
