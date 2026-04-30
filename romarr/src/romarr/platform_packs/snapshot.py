"""Snapshot loader + diff producer for platform-pack ingestion.

Both functions are pure relative to a captured DB snapshot — the
snapshot is loaded once at the start of ingestion, then the diff is
computed off the in-memory copy. This keeps the ingestor's hot path
free of redundant SELECTs and lets the validate-only endpoint reuse
the same diff logic without ever opening a write transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from romarr.domain.models import (
    Platform,
    PlatformFormat,
    PlatformNamingToken,
)
from romarr.platform_packs.models import ParsingStrategy

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.platform_packs.types import PackPlatformDiff


# Fields on Platform that a pack apply may overwrite (when not
# user-overridden). ``slug`` and ``id`` are intentionally excluded;
# ``pack_source`` / ``pack_version`` are stamped by the ingestor itself.
_MUTABLE_PLATFORM_FIELDS: tuple[str, ...] = (
    "name",
    "short_name",
    "manufacturer",
    "release_year",
    "igdb_id",
    "screenscraper_id",
    "mobygames_id",
    "launchbox_id",
    "retroachievements_id",
)


@dataclass(slots=True)
class PlatformSnapshot:
    """One platform's persisted state at the start of a pack apply."""

    id: int
    slug: str
    name: str
    short_name: str | None
    manufacturer: str | None
    release_year: int | None
    igdb_id: int | None
    screenscraper_id: int | None
    mobygames_id: int | None
    launchbox_id: int | None
    retroachievements_id: int | None
    parent_platform_slug: str | None
    pack_source: str
    pack_version: str | None
    extensions: dict[str, str]  # extension → format pack_source
    naming_tokens: dict[str, str]  # token name → token pack_source


@dataclass(slots=True)
class StrategySnapshot:
    """One parsing-strategy row's persisted state."""

    id: str
    pack_source: str
    pattern: str


@dataclass(slots=True)
class DBSnapshot:
    """Composite of every persistent piece the ingestor consults."""

    platforms_by_slug: dict[str, PlatformSnapshot] = field(default_factory=dict)
    strategies_by_id: dict[str, StrategySnapshot] = field(default_factory=dict)


async def load_snapshot(session: AsyncSession) -> DBSnapshot:
    """Read the current Platform / PlatformFormat / PlatformNamingToken
    / ParsingStrategy state into a :class:`DBSnapshot`.

    Single round-trip per table — no joins; the in-memory join happens
    on slug. The caller holds the session for the rest of ingestion,
    so the snapshot is consistent with the begin-block that follows.
    """
    snapshot = DBSnapshot()

    platforms = (
        (await session.execute(select(Platform))).scalars().all()
    )
    id_to_slug = {p.id: p.slug for p in platforms}

    for plat in platforms:
        parent_slug: str | None = None
        if plat.parent_platform_id is not None:
            parent_slug = id_to_slug.get(plat.parent_platform_id)
        snapshot.platforms_by_slug[plat.slug] = PlatformSnapshot(
            id=plat.id,
            slug=plat.slug,
            name=plat.name,
            short_name=plat.short_name,
            manufacturer=plat.manufacturer,
            release_year=plat.release_year,
            igdb_id=plat.igdb_id,
            screenscraper_id=plat.screenscraper_id,
            mobygames_id=plat.mobygames_id,
            launchbox_id=plat.launchbox_id,
            retroachievements_id=plat.retroachievements_id,
            parent_platform_slug=parent_slug,
            pack_source=plat.pack_source,
            pack_version=plat.pack_version,
            extensions={},
            naming_tokens={},
        )

    formats = (
        (await session.execute(select(PlatformFormat))).scalars().all()
    )
    for fmt in formats:
        slug = id_to_slug.get(fmt.platform_id)
        if slug is None:
            continue
        snap = snapshot.platforms_by_slug.get(slug)
        if snap is not None:
            snap.extensions[fmt.extension] = fmt.pack_source

    tokens = (
        (await session.execute(select(PlatformNamingToken))).scalars().all()
    )
    for tok in tokens:
        slug = id_to_slug.get(tok.platform_id)
        if slug is None:
            continue
        snap = snapshot.platforms_by_slug.get(slug)
        if snap is not None:
            snap.naming_tokens[tok.name] = tok.pack_source

    strategies = (
        (await session.execute(select(ParsingStrategy))).scalars().all()
    )
    for strat in strategies:
        snapshot.strategies_by_id[strat.id] = StrategySnapshot(
            id=strat.id,
            pack_source=strat.pack_source,
            pattern=strat.pattern,
        )

    return snapshot


def compute_platform_diff(
    parsed_platforms: list[dict[str, Any]],
    snapshot: DBSnapshot,
) -> list[PackPlatformDiff]:
    """Pure: build per-platform diff entries (insert / update / skip).

    Skipped reasons:
      - ``user-overridden`` — slug exists with ``pack_source = 'user'``,
        the FR-012 user-wins rule fires.
    """
    from romarr.platform_packs.types import PackPlatformDiff

    out: list[PackPlatformDiff] = []
    for plat in parsed_platforms:
        slug = plat["slug"]
        existing = snapshot.platforms_by_slug.get(slug)
        if existing is None:
            out.append(
                PackPlatformDiff(slug=slug, action="inserted", fields_changed=[])
            )
            continue
        if existing.pack_source == "user":
            out.append(
                PackPlatformDiff(
                    slug=slug,
                    action="skipped",
                    reason="user-overridden",
                )
            )
            continue
        # Build the field-changed list — anything in the pack that differs
        # from the persisted value, plus a synthetic "formats" /
        # "naming_tokens" entry whenever the set differs.
        changed: list[str] = []
        for fld in _MUTABLE_PLATFORM_FIELDS:
            if fld == "name":
                if plat.get("name") != existing.name:
                    changed.append("name")
            elif fld == "short_name":
                if plat.get("short_name") != existing.short_name:
                    changed.append("short_name")
            elif fld == "manufacturer":
                if plat.get("manufacturer") != existing.manufacturer:
                    changed.append("manufacturer")
            elif fld == "release_year":
                if plat.get("release_year") != existing.release_year:
                    changed.append("release_year")
            else:
                pack_value = (plat.get("metadata_ids") or {}).get(fld)
                if pack_value != getattr(existing, fld):
                    changed.append(fld)

        pack_extensions = {f["extension"] for f in plat.get("formats") or []}
        if pack_extensions != set(existing.extensions):
            changed.append("formats")
        pack_token_patterns = {
            tok["pattern"] for tok in plat.get("naming_tokens") or []
        }
        if pack_token_patterns != set(existing.naming_tokens):
            # token name is the slug-style derivation in the ingestor;
            # we surface "naming_tokens" as a coarse signal.
            changed.append("naming_tokens")

        if not changed:
            out.append(
                PackPlatformDiff(
                    slug=slug,
                    action="skipped",
                    reason="no_changes",
                )
            )
        else:
            out.append(
                PackPlatformDiff(
                    slug=slug,
                    action="updated",
                    fields_changed=changed,
                )
            )

    return out


__all__ = [
    "DBSnapshot",
    "PlatformSnapshot",
    "StrategySnapshot",
    "compute_platform_diff",
    "load_snapshot",
]
