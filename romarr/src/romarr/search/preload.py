"""Async helper that builds a :class:`LibraryState` from the database.

Per the plan's preload pattern, every search-mode round reads the
state ONCE, hands it to the pure pipeline, and never re-reads.

For MVP this preload is global — there's no per-Library scoping yet
(spec 009 introduces the FK columns). The round orchestrator picks
the factory-default profile per type when multiple exist; once the
library spec lands the orchestrator will look up the bound profile
ids per Library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import Game, Platform, PlatformFormat, Release
from romarr.indexers.models import Indexer
from romarr.profiles.models import (
    CustomFormat,
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)
from romarr.search.models import Blocklist
from romarr.search.state import (
    BlocklistEntry,
    IndexerMeta,
    LibraryState,
    MonitoredGame,
    MonitoredRelease,
    PlatformFormatBounds,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def preload_library_state(session: AsyncSession) -> LibraryState:
    """Read everything the pipeline consumes into a frozen snapshot.

    Pure across the duration of the round it serves; the round
    orchestrator passes this snapshot to every pipeline call so the
    pipeline never re-reads the DB (FR-016 purity).
    """
    games_rows = (await session.execute(select(Game))).scalars().all()
    monitored_games = tuple(
        MonitoredGame(
            id=row.id,
            platform_id=row.platform_id,
            title=row.title,
            sort_title=row.sort_title or "",
            alt_names=tuple(
                # alt_names not modelled on Game yet; consume from
                # custom_metadata when present.
                row.custom_metadata.get("alt_names", ())
                if isinstance(row.custom_metadata, dict)
                else ()
            ),
            year=(
                row.release_date.year if row.release_date is not None else None
            ),
            publisher=row.publisher or "",
            monitored=row.monitored,
        )
        for row in games_rows
    )

    releases_rows = (await session.execute(select(Release))).scalars().all()
    monitored_releases = tuple(
        MonitoredRelease(
            id=row.id,
            game_id=row.game_id,
            # Foundation Release stores ``regions`` as a list; search
            # consumes the first entry as the canonical region. Multi-
            # region releases still match via the pipeline's evaluator
            # which checks ``in`` semantics.
            region=(row.regions[0] if row.regions else ""),
            revision=row.revision or "",
            languages=tuple(row.languages or ()),
            dump_status=_safe_dump_status(row),
            naming_convention=_safe_naming_convention(row),
            # file_format lives on the Dump row; round orchestrator
            # looks it up there. For preload we leave it empty — the
            # pipeline's size-bounds gate is skipped when empty.
            file_format="",
            monitored=row.monitored,
        )
        for row in releases_rows
    )

    bounds_rows = (await session.execute(select(PlatformFormat))).scalars().all()
    platform_format_bounds = tuple(
        PlatformFormatBounds(
            platform_id=row.platform_id,
            extension=row.extension,
            min_size_bytes=row.min_size_bytes,
            max_size_bytes=row.max_size_bytes,
        )
        for row in bounds_rows
    )

    blocklist_rows = (await session.execute(select(Blocklist))).scalars().all()
    blocklist = tuple(
        BlocklistEntry(
            indexer_id=row.indexer_id,
            indexer_guid=row.indexer_guid or "",
            hash_sha1=(row.hash_sha1 or "").lower(),
            hash_crc32=(row.hash_crc32 or "").lower(),
            reason=row.reason,
        )
        for row in blocklist_rows
    )

    indexer_rows = (
        (await session.execute(select(Indexer))).scalars().all()
    )
    indexer_meta = tuple(
        IndexerMeta(
            id=row.id, priority=row.priority, min_seeders=row.min_seeders
        )
        for row in indexer_rows
    )

    return LibraryState(
        monitored_games=monitored_games,
        monitored_releases=monitored_releases,
        platform_format_bounds=platform_format_bounds,
        blocklist=blocklist,
        indexer_meta=indexer_meta,
    )


async def preload_default_profiles(
    session: AsyncSession,
) -> dict[str, object]:
    """Pick one profile per type — the factory-default seeded row when
    present, otherwise the first row by id.

    Returns a dict keyed by ``"quality" | "region" | "dump" |
    "language" | "naming"``. The orchestrator passes the matching
    entry to each evaluator in the pipeline.

    Custom formats (which evaluate as a list, not a single profile)
    are returned via :func:`preload_custom_formats`.
    """
    out: dict[str, object] = {}
    type_map = {
        "quality": QualityProfile,
        "region": RegionProfile,
        "dump": DumpProfile,
        "language": LanguageProfile,
        "naming": NamingProfile,
    }
    for label, model_cls in type_map.items():
        rows = (await session.execute(select(model_cls))).scalars().all()
        if not rows:
            out[label] = None
            continue
        # Prefer the factory-default seeded row; fall back to first by id.
        seeded = next(
            (r for r in rows if getattr(r, "is_factory_default", False)),
            None,
        )
        out[label] = (
            seeded
            if seeded is not None
            else min(rows, key=lambda r: getattr(r, "id", 0))
        )
    return out


async def preload_library_profiles(
    session: AsyncSession, library_id: int
) -> dict[str, object]:
    """Return the five profiles bound to one Library.

    Mirrors :func:`preload_default_profiles` but resolves each profile
    via the Library's FK columns. Used by the release-search round so
    the gate set matches the Library that owns the Release.
    """
    from romarr.libraries.models import Library

    library = (
        await session.execute(select(Library).where(Library.id == library_id))
    ).scalar_one_or_none()
    if library is None:
        return {
            "quality": None,
            "region": None,
            "dump": None,
            "language": None,
            "naming": None,
        }
    bindings = {
        "quality": (QualityProfile, library.quality_profile_id),
        "region": (RegionProfile, library.region_profile_id),
        "dump": (DumpProfile, library.dump_profile_id),
        "language": (LanguageProfile, library.language_profile_id),
        "naming": (NamingProfile, library.naming_profile_id),
    }
    out: dict[str, object] = {}
    for label, (model_cls, profile_id) in bindings.items():
        if profile_id is None:
            out[label] = None
            continue
        out[label] = (
            await session.execute(
                select(model_cls).where(model_cls.id == profile_id)
            )
        ).scalar_one_or_none()
    return out


async def preload_custom_formats(session: AsyncSession) -> list[CustomFormat]:
    """Return every Custom Format (no library scope until spec 009)."""
    return list((await session.execute(select(CustomFormat))).scalars().all())


async def preload_indexers(
    session: AsyncSession,
    *,
    indexer_ids: list[int] | None = None,
    require_rss: bool = False,
) -> list[Indexer]:
    """Return enabled indexer rows; optionally filtered by id or RSS gating.

    Slice 434 — actually respects the ``Indexer.enabled`` master
    switch (slice 432 added the column + chip; the registry's
    ``load_enabled`` honoured it but every search round goes
    through THIS preload helper instead, so disabled indexers
    were still showing up in manual search results, Wanted
    refresh, RSS polls, etc.). Filtering at the source means the
    three callers (manual / release / rss rounds) all benefit
    without each having to add their own predicate.
    """
    stmt = select(Indexer).where(Indexer.enabled.is_(True))
    if indexer_ids is not None:
        stmt = stmt.where(Indexer.id.in_(indexer_ids))
    rows = (await session.execute(stmt)).scalars().all()
    if require_rss:
        rows = [r for r in rows if r.enable_rss]
    return list(rows)


async def preload_platform(
    session: AsyncSession, platform_id: int
) -> Platform | None:
    return (
        await session.execute(select(Platform).where(Platform.id == platform_id))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_dump_status(row: Release) -> DumpStatus:
    raw = getattr(row, "dump_status", None)
    if isinstance(raw, DumpStatus):
        return raw
    if isinstance(raw, str):
        try:
            return DumpStatus(raw)
        except ValueError:
            return DumpStatus.UNKNOWN
    return DumpStatus.UNKNOWN


def _safe_naming_convention(row: Release) -> NamingConvention:
    raw = getattr(row, "naming_convention", None)
    if isinstance(raw, NamingConvention):
        return raw
    if isinstance(raw, str):
        try:
            return NamingConvention(raw)
        except ValueError:
            return NamingConvention.UNKNOWN
    return NamingConvention.UNKNOWN


__all__ = [
    "preload_custom_formats",
    "preload_default_profiles",
    "preload_indexers",
    "preload_library_state",
    "preload_platform",
]
