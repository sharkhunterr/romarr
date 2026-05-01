"""DB-update step (FR-027 / FR-028 / pipeline step 11).

After the MOVE step lands the file at its canonical destination,
this step persists the result:

  1. Insert a new :class:`Dump` row with every hash + DAT-match
     metadata + audit fields.
  2. If ``keep_dump_history=False`` (the library's default per
     FR-028), delete every prior :class:`Dump` row for the same
     :class:`Release`. The on-disk files for the old dumps are
     **NOT** removed here — that's the LIFECYCLE step's concern
     when the lifecycle policy requires it. Stale orphans stay
     until the operator runs the next library scan.
  3. Transition the :class:`Release.status` to ``'imported'`` and
     clear ``cutoff_met`` so the search engine can re-evaluate
     against the current Quality profile.

The whole operation runs in a single transaction so a failure
between steps doesn't leave the DB half-updated. Concurrent
callers serialise on the per-(release_id, sha1) advisory lock
the orchestrator already holds (see ``ImportLockManager``); this
step doesn't acquire its own lock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import delete, select

from romarr.domain.models import Dump, Release

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.identification.hasher import HashResult


_ImportedVia = Literal["automatic", "manual", "rss", "api", "webhook"]


async def persist_dump(
    *,
    session: AsyncSession,
    release_id: int,
    dump_path: Path,
    original_filename: str,
    hashes: HashResult,
    file_format: str,
    dat_verified: bool = False,
    dat_source: str | None = None,
    dat_entry_id: int | None = None,
    imported_via: _ImportedVia = "automatic",
    imported_by: str = "system",
    keep_dump_history: bool = False,
) -> Dump:
    """Insert the new Dump, optionally retire prior Dumps, and
    transition the Release.

    Returns the freshly-flushed :class:`Dump` row so the caller
    can record its id on the audit row.

    The caller is responsible for committing — this function calls
    ``await session.flush()`` so ``Dump.id`` is populated, but
    leaves transaction management to the orchestrator (which
    composes this step with LIFECYCLE / NOTIFY).
    """
    # 1. Retire prior Dumps when history is disabled (FR-028).
    if not keep_dump_history:
        await session.execute(
            delete(Dump).where(Dump.release_id == release_id)
        )

    # 2. Insert the fresh Dump row.
    now = datetime.now(UTC)
    dump = Dump(
        release_id=release_id,
        path=str(dump_path),
        original_filename=original_filename,
        size_bytes=hashes.size_bytes,
        format=file_format,
        crc32=hashes.crc32,
        md5=hashes.md5,
        sha1=hashes.sha1,
        sha256=hashes.sha256,
        dat_verified=dat_verified,
        dat_source=dat_source,
        dat_entry_id=dat_entry_id,
        imported_at=now,
        imported_by=imported_by,
        imported_via=imported_via,
    )
    session.add(dump)
    await session.flush()

    # 3. Transition the Release to imported.
    release = (
        await session.execute(
            select(Release).where(Release.id == release_id)
        )
    ).scalar_one()
    release.status = "imported"
    release.cutoff_met = False  # search engine will re-evaluate

    return dump


__all__ = ["persist_dump"]
