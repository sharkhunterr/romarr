"""Async blocklist helpers (Phase 4 — STATE / FR-021).

The blocklist is a global Romarr-instance suppression list (per
FR-020a: per-library scope is v1+). Releases are added either:

  * Manually by an operator via the API (added_by = operator id).
  * Automatically by the importer when a grab fails to verify
    against the DAT (added_by = "system" + structured reason).

The pipeline gates against the blocklist EARLY (steps 3-4), so
hits short-circuit before the expensive Custom Format scoring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, or_, select

from romarr.search.models import Blocklist

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.indexers.types import SearchResult


async def is_blocklisted(
    session: AsyncSession, *, result: SearchResult
) -> Blocklist | None:
    """Return the matching :class:`Blocklist` row or None.

    Lookup order: GUID match (fastest, most specific) > sha1 hash >
    crc32 hash. Hash comparisons are normalised to lowercase.
    """
    sha1 = (result.hash_sha1 or "").lower()
    crc = (result.hash_crc32 or "").lower()

    clauses: list[Any] = []
    if result.guid:
        clauses.append(
            (Blocklist.indexer_id == result.indexer_id)
            & (Blocklist.indexer_guid == result.guid)
        )
    if sha1:
        clauses.append(Blocklist.hash_sha1 == sha1)
    if crc:
        clauses.append(Blocklist.hash_crc32 == crc)
    if not clauses:
        return None

    return (
        await session.execute(select(Blocklist).where(or_(*clauses)).limit(1))
    ).scalar_one_or_none()


async def add_entry(
    session: AsyncSession,
    *,
    release_title: str,
    reason: str,
    indexer_id: int | None = None,
    indexer_guid: str | None = None,
    hash_sha1: str | None = None,
    hash_crc32: str | None = None,
    added_by: str = "system",
    now: datetime | None = None,
) -> Blocklist:
    """Insert a new blocklist row. Returns the persisted row.

    Rejection of the at-least-one-match-field invariant happens at
    the Pydantic schema layer (:class:`BlocklistCreate`); callers who
    skip validation get a save-time IntegrityError downstream, but
    this helper trusts its arguments.
    """
    row = Blocklist(
        indexer_id=indexer_id,
        indexer_guid=indexer_guid,
        release_title=release_title,
        hash_sha1=hash_sha1.lower() if hash_sha1 else None,
        hash_crc32=hash_crc32.lower() if hash_crc32 else None,
        reason=reason,
        added_by=added_by,
        added_at=now or datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_entry(session: AsyncSession, *, entry_id: int) -> bool:
    """Delete one blocklist row. Returns True iff it existed."""
    result: Any = await session.execute(
        delete(Blocklist).where(Blocklist.id == entry_id)
    )
    await session.commit()
    rowcount = getattr(result, "rowcount", 0) or 0
    return rowcount > 0


# CL006 / FR-021 (rewritten in the 2026-04-29 clarifications) —
# auto-blocklist ONLY for content-correctness failures. Transient
# subreasons (disk full, permissions, network, etc.) are recorded
# in ``search_history`` but should never blocklist the release —
# the next attempt could succeed against the same payload.
AUTO_BLOCKLIST_SUBREASONS: frozenset[str] = frozenset(
    {
        "hash-mismatch",
        "dat-rejected",
        "format-corrupt",
        "archive-extraction-failed",
    }
)
"""Failure subreasons that mean the payload itself is wrong, not
the environment. Adding to this set widens auto-blocklisting; do
NOT add transient codes here without a spec amendment."""

TRANSIENT_FAILURE_SUBREASONS: frozenset[str] = frozenset(
    {
        "disk-full",
        "permission-denied",
        "client-unreachable",
        "move-failed",
        "scan-timeout",
    }
)
"""Failure subreasons that mean the environment was wrong; the
payload may be fine. Documented exhaustively in spec 007 CL006 so
the audit trail is unambiguous about why a row didn't blocklist."""


def _strip_prefix(reason: str) -> str:
    """Return the bare subreason (no ``import-failed:`` prefix)."""
    if reason.startswith("import-failed:"):
        return reason.split(":", 1)[1]
    return reason


def is_auto_blocklist_subreason(reason: str) -> bool:
    """True iff the failure subreason is content-correctness.

    Used by the importer + the auto-blocklist trigger. Transient
    codes return False; unknown codes also return False (fail-safe:
    we'd rather miss an auto-blocklist than incorrectly suppress a
    release that just hit a flaky network)."""
    return _strip_prefix(reason) in AUTO_BLOCKLIST_SUBREASONS


async def auto_add_on_import_failure(
    session: AsyncSession,
    *,
    result: SearchResult,
    reason: str,
) -> Blocklist | None:
    """Importer entry-point: blocklist a release after a failed import.

    Only fires for content-correctness subreasons (CL006 / FR-021).
    Returns ``None`` for transient subreasons so the importer's
    history-write path can still record the failure without
    suppressing the release on the next round.

    The reason is structured (``"import-failed:<code>"``) so the
    history view can group by failure mode. The pipeline's blocklist
    gate consults the row on the next round and short-circuits before
    re-grabbing.
    """
    if not is_auto_blocklist_subreason(reason):
        return None
    return await add_entry(
        session,
        indexer_id=result.indexer_id,
        indexer_guid=result.guid,
        release_title=result.title,
        hash_sha1=result.hash_sha1,
        hash_crc32=result.hash_crc32,
        reason=f"import-failed:{reason}" if not reason.startswith("import-failed:") else reason,
        added_by="system",
    )


__all__ = [
    "AUTO_BLOCKLIST_SUBREASONS",
    "TRANSIENT_FAILURE_SUBREASONS",
    "add_entry",
    "auto_add_on_import_failure",
    "delete_entry",
    "is_auto_blocklist_subreason",
    "is_blocklisted",
]
