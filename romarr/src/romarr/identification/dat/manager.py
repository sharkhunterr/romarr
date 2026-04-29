"""DatManager — async ingestion + per-platform DAT lookups.

Implements FR-017 / FR-018 / FR-019 / FR-020 plus the cross-DAT
precedence resolver from CL001 (FR-020a):

  - ``ingest()`` streams a Logiqx DAT into ``dat_entry`` rows. Calling
    ingest twice on the same DAT body is a no-op (FR-019, idempotent
    via ``contents_hash``).
  - ``lookup_by_sha1`` / ``lookup_by_crc32`` / ``lookup_by_md5`` /
    ``lookup_by_name`` — FR-018 lookups, scoped to a Platform.
  - ``best_match_by_sha1`` — applies FR-020a authority order
    **No-Intro > Redump > TOSEC** when a single hash matches entries
    from multiple sources; the first match wins as the canonical
    metadata; the others are returned alongside as supporting
    matches in the conflict log.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from romarr.domain.enums import DumpStatus
from romarr.domain.models import DatEntry
from romarr.identification.dat.logiqx import parse_logiqx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Per CL001 / FR-020a — the canonical cross-DAT precedence order.
DAT_AUTHORITY_ORDER: tuple[str, ...] = (
    "no-intro",
    "redump",
    "tosec",
    "goodtools",
    "hasheous",
    "playmatch",
    "custom",
)

_AUTHORITY_RANK: dict[str, int] = {
    src: idx for idx, src in enumerate(DAT_AUTHORITY_ORDER)
}


# ---------------------------------------------------------------------------
# Public results
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IngestStats:
    """Outcome summary for an :meth:`DatManager.ingest` call."""

    inserted: int
    skipped_idempotent: bool
    contents_hash: str


@dataclass(frozen=True, slots=True)
class DatBestMatch:
    """Result of :meth:`DatManager.best_match_by_sha1`.

    ``winner`` is the highest-authority entry (per CL001). ``losers``
    contains every other entry that matched the same hash — these are
    the "supporting matches" to record in the merger's conflict log.
    """

    winner: DatEntry
    losers: tuple[DatEntry, ...]


# ---------------------------------------------------------------------------
# DatManager
# ---------------------------------------------------------------------------


class DatManager:
    """Async DAT ingestion + lookup."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest(
        self,
        *,
        platform_id: int,
        source: str,
        dat_path: str | PathLike[str] | None = None,
        dat_bytes: bytes | None = None,
    ) -> IngestStats:
        """Ingest a Logiqx DAT for ``platform_id`` from ``source``.

        Provide either ``dat_path`` (file on disk) or ``dat_bytes``
        (in-memory bytes — used by tests / API uploads).

        Idempotent per FR-019: a DAT whose ``contents_hash`` already
        exists in the database is a no-op (``skipped_idempotent=True``).
        ``contents_hash`` is the SHA-256 of the raw DAT body — same
        bytes ⇒ same hash ⇒ same outcome.
        """
        if (dat_path is None) == (dat_bytes is None):
            raise ValueError(
                "exactly one of dat_path or dat_bytes must be supplied"
            )
        if source not in _AUTHORITY_RANK:
            raise ValueError(
                f"unknown DAT source {source!r}; expected one of "
                f"{DAT_AUTHORITY_ORDER!r}"
            )

        # Compute contents_hash up front so we can short-circuit on a
        # known DAT before any parsing.
        if dat_bytes is None:
            assert dat_path is not None  # narrowed by the XOR check above
            dat_bytes = Path(dat_path).read_bytes()
        contents_hash = hashlib.sha256(dat_bytes).hexdigest()

        # FR-019 idempotency check.
        existing = await self._session.execute(
            select(DatEntry.id)
            .where(
                DatEntry.platform_id == platform_id,
                DatEntry.source == source,
                DatEntry.dat_contents_hash == contents_hash,
            )
            .limit(1)
        )
        if existing.first() is not None:
            return IngestStats(
                inserted=0,
                skipped_idempotent=True,
                contents_hash=contents_hash,
            )

        # Stream-parse + bulk-insert.
        rows: list[dict[str, object]] = []
        for rom in parse_logiqx(dat_bytes):
            if not (rom.crc32 or rom.md5 or rom.sha1):
                # FR-006 — skip rows with no usable hash at all.
                continue
            rows.append(
                {
                    "platform_id": platform_id,
                    "source": source,
                    "name": rom.parent_game_name or rom.rom_name,
                    "description": rom.description,
                    "size_bytes": rom.size_bytes,
                    "crc32": rom.crc32,
                    "md5": rom.md5,
                    "sha1": rom.sha1,
                    "status": DumpStatus.VERIFIED.value,
                    "dat_contents_hash": contents_hash,
                }
            )

        # Insert with ON CONFLICT DO NOTHING on the
        # ``(platform_id, source, sha1)`` unique constraint so a
        # partial historical re-run is also safe.
        if rows:
            stmt = sqlite_insert(DatEntry).values(rows)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["platform_id", "source", "sha1"]
            )
            await self._session.execute(stmt)
            await self._session.commit()

        return IngestStats(
            inserted=len(rows),
            skipped_idempotent=False,
            contents_hash=contents_hash,
        )

    # ------------------------------------------------------------------
    # Lookups (FR-018)
    # ------------------------------------------------------------------

    async def lookup_by_sha1(
        self, *, platform_id: int, sha1: str
    ) -> list[DatEntry]:
        """Return every DAT entry whose SHA-1 matches, scoped to platform."""
        result = await self._session.execute(
            select(DatEntry).where(
                DatEntry.platform_id == platform_id,
                DatEntry.sha1 == sha1.lower(),
            )
        )
        return list(result.scalars().all())

    async def lookup_by_crc32(
        self, *, platform_id: int, crc32: str
    ) -> list[DatEntry]:
        result = await self._session.execute(
            select(DatEntry).where(
                DatEntry.platform_id == platform_id,
                DatEntry.crc32 == crc32.lower(),
            )
        )
        return list(result.scalars().all())

    async def lookup_by_md5(
        self, *, platform_id: int, md5: str
    ) -> list[DatEntry]:
        result = await self._session.execute(
            select(DatEntry).where(
                DatEntry.platform_id == platform_id,
                DatEntry.md5 == md5.lower(),
            )
        )
        return list(result.scalars().all())

    async def lookup_by_name(
        self, *, platform_id: int, name: str
    ) -> list[DatEntry]:
        result = await self._session.execute(
            select(DatEntry).where(
                DatEntry.platform_id == platform_id,
                DatEntry.name == name,
            )
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Cross-DAT precedence (CL001 / FR-020a)
    # ------------------------------------------------------------------

    async def best_match_by_sha1(
        self, *, platform_id: int, sha1: str
    ) -> DatBestMatch | None:
        """Return the highest-authority entry for a SHA-1 match.

        Per CL001: when the same SHA-1 matches DAT entries from
        multiple sources, **No-Intro > Redump > TOSEC** wins. The
        winning entry's metadata is canonical; supporting matches are
        returned as ``losers`` so the merger can record them in the
        conflict log without losing information.
        """
        matches = await self.lookup_by_sha1(platform_id=platform_id, sha1=sha1)
        return _resolve_authority(matches)


def _resolve_authority(matches: list[DatEntry]) -> DatBestMatch | None:
    """Pure-function helper — given matched entries, pick the highest authority.

    Exposed for unit testing without a database.
    """
    if not matches:
        return None
    sorted_matches = sorted(
        matches,
        key=lambda e: (_AUTHORITY_RANK.get(e.source, 999), e.id),
    )
    winner = sorted_matches[0]
    losers = tuple(sorted_matches[1:])
    return DatBestMatch(winner=winner, losers=losers)
