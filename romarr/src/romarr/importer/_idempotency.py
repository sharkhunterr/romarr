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


__all__ = ["find_existing_dump"]
