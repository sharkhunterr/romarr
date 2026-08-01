"""Materialize a live ``Platform`` row from the stack of per-source contributions.

Introduced by migration 0044 to power the ``prefer`` binding mode
and automatic array fusion across community sources. Rules :

  * **skip binding** — the source's contribution for this slug is
    dropped entirely (already honoured at ingest, re-honoured here
    for defence-in-depth).
  * **prefer binding** — this source wins scalar fields for the
    slug even if another source has a higher rank / applied more
    recently.
  * **arrays** — always union-merged across every non-skipped
    contribution : ``aliases``, ``newznab_category_ids``, plus
    ``formats`` (dedup by extension) and ``naming_tokens`` (dedup
    by name). This is the "fusion" behaviour the operator asked
    for — a slug served by two packs picks up the aliases + format
    coverage of both.
  * **scalar fallback** — when no source has ``prefer`` for the
    slug, the winner is the highest-ranked contributor per
    ``platform_pack_config.source_order``. Sources not in the
    order rank below listed ones, ordered by id. Absolute-last
    fallback : the contribution with the latest ``applied_at``.

Non-community rows (``pack_source_id IS NULL``, e.g. legacy builtin
or user-created) are left untouched — the materializer never runs
on a slug that has zero community contributions.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import (
    Platform,
    PlatformFormat,
    PlatformNamingToken,
)
from romarr.platform_packs.models import (
    PlatformPackConfig,
    PlatformSourceBinding,
    PlatformSourceContribution,
)

_LOG = logging.getLogger(__name__)


def _snapshot_platform(
    plat: dict[str, Any],
    *,
    formats: list[dict[str, Any]],
    naming_tokens: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the JSON blob stored in
    ``platform_source_contribution.contribution``.

    Every field the materializer reads back has to be here; missing
    fields become None / empty at read-time.
    """
    meta_ids = plat.get("metadata_ids") or {}
    return {
        "name": plat["name"],
        "short_name": plat.get("short_name"),
        "manufacturer": plat.get("manufacturer"),
        "release_year": plat.get("release_year"),
        "aliases": list(plat.get("aliases") or []),
        "igdb_id": meta_ids.get("igdb_id"),
        "screenscraper_id": meta_ids.get("screenscraper_id"),
        "mobygames_id": meta_ids.get("mobygames_id"),
        "launchbox_id": meta_ids.get("launchbox_id"),
        "retroachievements_id": meta_ids.get("retroachievements_id"),
        "newznab_category_ids": list(plat.get("newznab_category_ids") or []),
        "formats": [dict(f) for f in formats],
        "naming_tokens": [dict(t) for t in naming_tokens],
    }


async def snapshot_contribution(
    session: AsyncSession,
    *,
    source_id: int,
    platform_slug: str,
    contribution: dict[str, Any],
    pack_version: str | None,
) -> None:
    """Upsert the ``(source_id, platform_slug)`` snapshot row.

    Called at the end of each per-platform ingest so the stack of
    contributions is always fresh. Idempotent on same-content
    re-application.
    """
    existing = await session.get(
        PlatformSourceContribution, (source_id, platform_slug)
    )
    now = datetime.now(UTC)
    if existing is None:
        session.add(
            PlatformSourceContribution(
                source_id=source_id,
                platform_slug=platform_slug,
                contribution=contribution,
                pack_version=pack_version,
                applied_at=now,
            )
        )
        return
    existing.contribution = contribution
    existing.pack_version = pack_version
    existing.applied_at = now


# ---------------------------------------------------------------------------
# Materialize
# ---------------------------------------------------------------------------


def _rank_key(
    source_id: int, order: list[int]
) -> tuple[int, int]:
    """Sort key: lower is better. Listed sources rank by index,
    others rank after with id as tie-break."""
    try:
        return (0, order.index(source_id))
    except ValueError:
        return (1, source_id)


async def materialize_platform(
    session: AsyncSession, *, platform_slug: str
) -> None:
    """Rewrite the live ``Platform`` row for ``platform_slug`` from the
    stack of community contributions + bindings.

    No-op when :
      * zero community contributions exist (nothing to materialize —
        the row keeps whatever the legacy code path wrote), OR
      * the live row is user-locked (``pack_source == "user"``).
    """
    # 1) load contributions
    contribs = (
        (
            await session.execute(
                select(PlatformSourceContribution).where(
                    PlatformSourceContribution.platform_slug == platform_slug
                )
            )
        )
        .scalars()
        .all()
    )
    if not contribs:
        return

    # 2) load bindings for these sources
    binding_rows = (
        (
            await session.execute(
                select(PlatformSourceBinding).where(
                    PlatformSourceBinding.platform_slug == platform_slug,
                    PlatformSourceBinding.source_id.in_(
                        [c.source_id for c in contribs]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    bindings_by_source: dict[int, str] = {
        b.source_id: b.mode for b in binding_rows
    }

    # 3) drop skipped contributions
    live = [
        c
        for c in contribs
        if bindings_by_source.get(c.source_id) != "skip"
    ]
    if not live:
        # Every contribution is skipped — nothing to write. Leave
        # the live Platform row untouched.
        return

    # 4) load global source_order (config singleton)
    cfg = (
        await session.execute(
            select(PlatformPackConfig).where(PlatformPackConfig.id == 1)
        )
    ).scalar_one_or_none()
    order: list[int] = list(cfg.source_order) if cfg is not None else []

    # 5) pick the scalar winner
    preferred = [
        c
        for c in live
        if bindings_by_source.get(c.source_id) == "prefer"
    ]
    if preferred:
        # Multiple prefer bindings — pick the highest-ranked.
        preferred.sort(key=lambda c: _rank_key(c.source_id, order))
        scalar_winner = preferred[0]
    else:
        # No prefer — pick by rank; ties broken by latest applied.
        live_sorted = sorted(
            live,
            key=lambda c: (
                _rank_key(c.source_id, order),
                -c.applied_at.timestamp(),
            ),
        )
        scalar_winner = live_sorted[0]

    # 6) load the target Platform row
    target = (
        await session.execute(
            select(Platform).where(Platform.slug == platform_slug)
        )
    ).scalar_one_or_none()
    if target is None:
        # First materialize — a live row hasn't been written yet;
        # the ingest path handles the initial insert. Nothing to do
        # here on the first pass. Once inserted, subsequent
        # materialize calls will find it and update.
        return
    if target.pack_source == "user":
        # FR-012 — operator's manual edits are sacred.
        return

    # 7) rewrite scalars from the winner
    w = scalar_winner.contribution
    target.name = w.get("name") or target.name
    target.short_name = w.get("short_name")
    target.manufacturer = w.get("manufacturer") or target.manufacturer
    target.release_year = w.get("release_year")
    target.igdb_id = w.get("igdb_id")
    target.screenscraper_id = w.get("screenscraper_id")
    target.mobygames_id = w.get("mobygames_id")
    target.launchbox_id = w.get("launchbox_id")
    target.retroachievements_id = w.get("retroachievements_id")
    target.pack_source = "community"
    target.pack_source_id = scalar_winner.source_id

    # 8) union arrays across every live contribution
    aliases = _union_preserving_order(
        [c.contribution.get("aliases") or [] for c in live]
    )
    target.aliases = aliases

    newznab_ids = _union_preserving_order(
        [c.contribution.get("newznab_category_ids") or [] for c in live]
    )
    target.newznab_category_ids = newznab_ids

    # 9) rewrite child tables: formats (dedup by extension)
    await _rewrite_formats(session, platform_id=target.id, live=live)

    # 10) rewrite child tables: naming tokens (dedup by name)
    await _rewrite_naming_tokens(session, platform_id=target.id, live=live)


def _union_preserving_order(lists: list[list[Any]]) -> list[Any]:
    """Concatenate lists, dropping duplicates while preserving the
    first-seen order. Case-sensitive for strings — packs are expected
    to normalise before publishing."""
    seen: set[str] = set()
    out: list[Any] = []
    for lst in lists:
        for item in lst:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


async def _rewrite_formats(
    session: AsyncSession,
    *,
    platform_id: int,
    live: list[PlatformSourceContribution],
) -> None:
    """Delete + re-insert the platform's formats from the union of
    every live contribution. Dedup key is ``extension``; first
    non-empty wins on min/max size."""
    seen: dict[str, dict[str, Any]] = {}
    for c in live:
        for fmt in c.contribution.get("formats") or []:
            ext = str(fmt.get("extension") or "").lower().lstrip(".")
            if not ext or ext in seen:
                continue
            seen[ext] = fmt

    await session.execute(
        delete(PlatformFormat).where(PlatformFormat.platform_id == platform_id)
    )
    for ext, fmt in seen.items():
        session.add(
            PlatformFormat(
                platform_id=platform_id,
                extension=ext,
                format_type=str(fmt.get("format_type") or "cartridge"),
                min_size_bytes=fmt.get("min_size_bytes"),
                max_size_bytes=fmt.get("max_size_bytes"),
                pack_source="community",
            )
        )


async def _rewrite_naming_tokens(
    session: AsyncSession,
    *,
    platform_id: int,
    live: list[PlatformSourceContribution],
) -> None:
    """Delete + re-insert naming tokens from the union of every
    live contribution. Dedup key is ``name``."""
    seen: dict[str, dict[str, Any]] = {}
    for c in live:
        for tok in c.contribution.get("naming_tokens") or []:
            name = str(tok.get("name") or "")
            if not name or name in seen:
                continue
            seen[name] = tok

    await session.execute(
        delete(PlatformNamingToken).where(
            PlatformNamingToken.platform_id == platform_id
        )
    )
    for name, tok in seen.items():
        session.add(
            PlatformNamingToken(
                platform_id=platform_id,
                name=name,
                pattern=str(tok.get("pattern") or ""),
                meaning=str(tok.get("meaning") or ""),
                convention=tok.get("convention") or "no-intro",
                pack_source="community",
            )
        )


async def materialize_all_slugs(
    session: AsyncSession, *, slugs: list[str]
) -> None:
    """Run :func:`materialize_platform` for each slug in ``slugs``.

    Called at the tail of ingest_pack (for touched slugs) and by
    the API when bindings / source_order change (for every slug
    the source has ever contributed to)."""
    for slug in slugs:
        await materialize_platform(session, platform_slug=slug)


__all__ = [
    "materialize_all_slugs",
    "materialize_platform",
    "snapshot_contribution",
    "_snapshot_platform",
]
