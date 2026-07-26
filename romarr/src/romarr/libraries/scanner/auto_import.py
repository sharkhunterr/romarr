"""Auto-import unmatched files during a library scan.

Turns the scanner from a plain "index-refresher for existing Dumps"
(spec 009 baseline) into what operators actually expect from a
"Scan" button: any file dropped into the library folder shows up as
a Game with a Release + Dump attached, best-effort identified.

Fallback ladder for a fresh file :

  1. **DAT match by SHA-1** — if a DAT source has been ingested for
     the file's platform, look up its canonical name. Wins on
     ``dat_verified=True`` and overwrites the parsed title.
  2. **Filename parse** — regex dispatcher extracts title / regions
     / revision / languages / naming convention. Powers the
     baseline case where no DAT + no metadata provider are set up.
  3. Nothing else — the stem of the filename is the last-resort
     title.

Metadata provider (IGDB / MobyGames / ScreenScraper) enrichment is
intentionally NOT in this function : it belongs to the metadata
aggregator (spec 002) which runs later on a background job. The
game shows up in the UI immediately with just the parsed name, and
metadata trickles in afterwards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Dump, Game, Platform, PlatformFormat, Release
from romarr.identification.dat.manager import DatManager
from romarr.identification.parsers import default_dispatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.identification.hasher import HashResult


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    """Convert a title to a lowercase kebab slug — used for the
    ``Game.slug`` uniqueness key.
    """
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "untitled"


@dataclass(frozen=True, slots=True)
class AutoIngestOutcome:
    """Result of a single ``auto_ingest_file`` call."""

    path: Path
    status: str  # "ingested" | "skipped" | "failed"
    game_id: int | None = None
    release_id: int | None = None
    dump_id: int | None = None
    dat_verified: bool = False
    reason: str | None = None


async def _resolve_platform_id(
    session: AsyncSession, *, extension: str
) -> int | None:
    """Return the platform whose format list includes ``extension``.

    Returns None if no platform claims that extension, OR if MORE
    than one does (ambiguous — e.g. `.zip` matches nearly every
    platform, so the file needs manual triage rather than a wrong
    guess). ``extension`` may include or omit the leading dot.
    """
    ext = extension if extension.startswith(".") else f".{extension}"
    matches = (
        await session.execute(
            select(PlatformFormat.platform_id)
            .where(PlatformFormat.extension == ext)
            .distinct()
        )
    ).scalars().all()
    # Exactly-one wins; ambiguous or absent = None (skip).
    return int(matches[0]) if len(matches) == 1 else None


async def auto_ingest_file(
    session: AsyncSession,
    *,
    file_path: Path,
    hash_result: HashResult,
    library_id: int,
    size_bytes: int,
    imported_by: str = "scanner",
) -> AutoIngestOutcome:
    """Create Game + Release + Dump rows for a freshly-scanned file.

    Caller MUST hold an open session and is responsible for the
    commit. Never raises on identification miss — the function
    always resolves to an :class:`AutoIngestOutcome` whose
    ``status`` field the caller reads. Real exceptions (DB
    integrity, hash mismatch) bubble up.
    """
    ext = file_path.suffix
    platform_id = await _resolve_platform_id(session, extension=ext)
    if platform_id is None:
        return AutoIngestOutcome(
            path=file_path,
            status="skipped",
            reason=f"no platform registered for extension {ext!r}",
        )

    # DAT match first — its canonical name overrides the filename
    # parse (which strips region tags but keeps typos / abbreviations).
    dat_best = None
    try:
        dat_best = await DatManager(session).best_match_by_sha1(
            platform_id=platform_id, sha1=hash_result.sha1
        )
    except Exception:  # noqa: BLE001 — never block a scan on DAT lookup
        dat_best = None
    dat_verified = False
    dat_source: str | None = None
    dat_entry_id: int | None = None
    dat_name: str | None = None
    if dat_best is not None:
        w = dat_best.winner
        dat_verified = w.status == DumpStatus.VERIFIED.value
        dat_source = w.source
        dat_entry_id = w.id
        dat_name = w.name

    # Filename parse — used for regions/languages/revision even when
    # DAT wins the name battle.
    parsed = default_dispatcher().parse(file_path.name)
    parsed_title = (parsed.title or "").strip()

    # Game.title priority : parsed title (region-stripped, human) >
    # DAT name (has region tags baked in) > filename stem.
    game_title = (
        parsed_title
        or (dat_name.split(" (")[0].strip() if dat_name else "")
        or file_path.stem
    )
    slug = _slugify(game_title)

    # Get or create the Game — dedup by (platform_id, slug).
    game = (
        await session.execute(
            select(Game).where(
                Game.platform_id == platform_id, Game.slug == slug
            )
        )
    ).scalar_one_or_none()
    if game is None:
        game = Game(
            platform_id=platform_id,
            slug=slug,
            title=game_title,
            monitored=True,
            needs_metadata_refresh=True,
            library_id=library_id,
        )
        session.add(game)
        await session.flush()  # populate game.id for the Release FK

    # Release name : full canonical DAT name (region-tagged) when
    # we have it, otherwise the raw filename stem.
    release_name = dat_name or file_path.stem

    # Reuse an existing Release with the same identity on this Game.
    existing_release = (
        await session.execute(
            select(Release).where(
                Release.game_id == game.id,
                Release.name == release_name,
            )
        )
    ).scalar_one_or_none()
    if existing_release is not None:
        release = existing_release
    else:
        release = Release(
            game_id=game.id,
            name=release_name,
            original_name=file_path.name,
            regions=list(parsed.regions),
            languages=list(parsed.languages),
            revision=parsed.revision,
            naming_convention=(
                NamingConvention(parsed.convention.value)
                if hasattr(parsed.convention, "value")
                else NamingConvention.UNKNOWN
            ),
            dump_status=(
                DumpStatus.VERIFIED if dat_verified else DumpStatus.UNKNOWN
            ),
            status="imported",
            library_id=library_id,
        )
        session.add(release)
        await session.flush()

    # Dump — path is globally unique so a rescan re-uses the existing
    # row and just refreshes size + hashes if the file changed.
    dump = (
        await session.execute(select(Dump).where(Dump.path == str(file_path)))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if dump is None:
        dump = Dump(
            release_id=release.id,
            path=str(file_path),
            original_filename=file_path.name,
            size_bytes=size_bytes,
            format=ext.lstrip("."),
            crc32=hash_result.crc32,
            md5=hash_result.md5,
            sha1=hash_result.sha1,
            dat_verified=dat_verified,
            dat_source=dat_source,
            dat_entry_id=dat_entry_id,
            imported_at=now,
            imported_by=imported_by,
            imported_via="scan",
        )
        session.add(dump)
        await session.flush()
    else:
        dump.release_id = release.id
        dump.size_bytes = size_bytes
        dump.crc32 = hash_result.crc32
        dump.md5 = hash_result.md5
        dump.sha1 = hash_result.sha1
        dump.dat_verified = dat_verified
        dump.dat_source = dat_source
        dump.dat_entry_id = dat_entry_id
        dump.imported_via = "scan"

    return AutoIngestOutcome(
        path=file_path,
        status="ingested",
        game_id=game.id,
        release_id=release.id,
        dump_id=dump.id,
        dat_verified=dat_verified,
    )


__all__ = ["AutoIngestOutcome", "auto_ingest_file"]
