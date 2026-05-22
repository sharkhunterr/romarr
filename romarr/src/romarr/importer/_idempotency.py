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


__all__ = ["find_dump_by_hash", "find_existing_dump"]
