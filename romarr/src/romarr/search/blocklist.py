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


async def auto_add_on_import_failure(
    session: AsyncSession,
    *,
    result: SearchResult,
    reason: str,
) -> Blocklist:
    """Importer entry-point: blocklist a release after a failed import.

    The reason is structured (``"import-failed:<code>"``) so the
    history view can group by failure mode. The pipeline's blocklist
    gate consults the row on the next round and short-circuits before
    re-grabbing.
    """
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
    "add_entry",
    "auto_add_on_import_failure",
    "delete_entry",
    "is_blocklisted",
]
