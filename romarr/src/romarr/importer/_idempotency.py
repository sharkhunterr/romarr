"""Coalesce-check helper for the orchestrator (slice 81).

Per FR-018 and FR-006, the importer is idempotent: re-importing
the same file for the same Release produces no state change.
The orchestrator runs identification first (to learn the
release_id) and then asks this module "have I already imported
this exact file for this release?" — if yes, the pipeline
short-circuits, records a `coalesced=True` history row, and
returns the original Dump's identity in the outcome.

The check is keyed on (release_id, sha1):

  * **release_id** — the file is "for this release" semantically.
    A Sonic dump that lives under a different Release (USA vs
    JPN, hack vs verified) is NOT a coalesce candidate; the
    orchestrator would route the SHA-1 collision through the
    destination-collision branch instead.
  * **sha1** — the canonical content hash. CRC32 / MD5 are
    hash-cascade signals only; sha1 is the persistent identity
    on the Dump row.

When the helper returns a Dump, the orchestrator skips the
RENDER / MOVE / DBUPDATE steps and emits OnImport with
``coalesced=True`` (FR-031).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.domain.models import Dump

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def find_existing_dump(
    *,
    session: AsyncSession,
    sha1: str,
    release_id: int,
) -> Dump | None:
    """Return the existing :class:`Dump` for the
    ``(release_id, sha1)`` pair, or ``None`` when this exact
    content has never been imported for this Release.

    The SHA-1 lookup is case-insensitive — every persisted
    `Dump.sha1` is lowercase by convention (the hasher emits
    lowercase) but accepting a mixed-case input lets the
    orchestrator pass the cascade's raw value through without
    normalising at the call site.
    """
    sha1_lower = sha1.lower()
    return (
        await session.execute(
            select(Dump).where(
                Dump.release_id == release_id,
                Dump.sha1 == sha1_lower,
            )
        )
    ).scalar_one_or_none()


async def find_dump_by_hash(
    *,
    session: AsyncSession,
    sha1: str,
) -> Dump | None:
    """Return ANY existing :class:`Dump` with this SHA-1, whatever
    Release it belongs to — or ``None`` when the content has never
    been imported.

    Unlike :func:`find_existing_dump` (keyed on release_id + sha1),
    this is a content-only lookup. The orchestrator uses it as a
    last guard before parking a ``match:no_game`` failure: when
    GAMEMATCH can't tie a file to a game but its hash is already a
    known imported Dump, the file is a duplicate of existing content
    (a leftover archive the watcher re-dispatched, a meta-torrent
    plus a standalone grab of the same ROM, …) — a coalesced
    success, not a failure.
    """
    return (
        await session.execute(
            select(Dump).where(Dump.sha1 == sha1.lower()).limit(1)
        )
    ).scalar_one_or_none()


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_stem(name: str) -> str:
    """Lower-case + strip extensions + collapse non-alphanumeric
    runs to a single space.

    Lets us compare a qBit-mangled archive filename
    ``Castlevania - Legacy of Darkness _USA_.zip`` against the
    canonical extracted ROM filename stored on
    ``Dump.original_filename``
    ``Castlevania - Legacy of Darkness (USA).z64``.

    Both normalize to ``castlevania legacy of darkness usa`` so
    the dispatch-race coalesce below recognises them as the same
    logical content.
    """
    # Strip every trailing suffix (``.zip``, ``.tar.gz``…) by
    # peeling alphanumeric runs that look like extensions.
    stem = name
    for _ in range(3):
        i = stem.rfind(".")
        if i > 0 and i >= len(stem) - 8 and stem[i + 1 :].isalnum():
            stem = stem[:i]
        else:
            break
    return _NORMALIZE_RE.sub(" ", stem.lower()).strip()


async def find_dump_by_filename(
    *,
    session: AsyncSession,
    source_filename: str,
    within: timedelta = timedelta(minutes=15),
) -> Dump | None:
    """Return a recently-imported :class:`Dump` whose
    ``original_filename`` normalizes to the same token-stripped
    stem as ``source_filename``, or ``None`` when no candidate
    exists.

    This is the *third* coalesce guard, after
    :func:`find_existing_dump` (release_id + sha1) and
    :func:`find_dump_by_hash` (sha1 only). It catches the
    dispatch-race case where a sibling event already imported and
    deleted the source file before this run could compute a hash:

      * qBit fires two events for one logical torrent — a generic
        directory-scan and a per-torrent completion. The first
        wins the race, extracts + hashes + imports + deletes; the
        second arrives moments later, finds the source missing,
        skips the hash step, and would otherwise be parked as a
        bogus ``match:no_game`` failure.
      * Stem normalisation tolerates qBit's
        ``(USA)`` → ``_USA_`` mangling and the archive→ROM
        extension change (``.zip`` → ``.z64``).

    Scoped to the recent past (default 15 min) so an unrelated
    coincidence months apart can't be mistaken for a sibling.
    """
    target = _normalize_stem(source_filename)
    if not target:
        return None
    cutoff = datetime.now(UTC) - within
    rows = (
        await session.execute(
            select(Dump)
            .where(Dump.imported_at.is_not(None), Dump.imported_at >= cutoff)
            .order_by(Dump.imported_at.desc())
            .limit(20)
        )
    ).scalars().all()
    for dump in rows:
        if _normalize_stem(dump.original_filename) == target:
            return dump
    return None


__all__ = [
    "find_dump_by_filename",
    "find_dump_by_hash",
    "find_existing_dump",
]
