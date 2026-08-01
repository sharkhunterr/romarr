"""Transactional pack ingestor (T032).

End-to-end pipeline:

  1. Validate the YAML body via :func:`validate_pack`.
  2. Load a DB snapshot (Platform + PlatformFormat + PlatformNamingToken
     + ParsingStrategy state at the start of the run).
  3. Compute the per-platform diff against that snapshot.
  4. Idempotency: if ``(pack_version, contents_hash)`` is already
     recorded in ``platform_pack`` → emit a ``skipped`` audit row,
     return without touching anything (FR-009).
  5. Conflict: if ``pack_version`` is already recorded with a
     different hash → raise :class:`PackVersionConflictError` (FR-010).
  6. Open a single ``async with session.begin():`` block:
       - per-platform: insert / update / skip per FR-011, FR-012, FR-013
       - per-strategy: upsert / skip per FR-014
       - insert one new ``platform_pack`` row
       - patch parent_platform_id post-pass (parents may live in the
         same pack or already in DB)
       - mark the audit row complete
  7. On any exception in step 6 the whole transaction rolls back; the
     audit row is persisted in a fresh session as ``status='failed'``
     (FR-007, FR-024) and the exception re-raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

from romarr.domain.models import (
    Platform,
    PlatformFormat,
    PlatformNamingToken,
    PlatformPack,
)
from romarr.platform_packs.audit import complete_log, fail_log, start_log
from romarr.platform_packs.errors import PackVersionConflictError
from romarr.platform_packs.models import ParsingStrategy
from romarr.platform_packs.snapshot import (
    DBSnapshot,
    compute_platform_diff,
    load_snapshot,
)
from romarr.platform_packs.types import PackPlatformDiff, PackUploadResult
from romarr.platform_packs.validator import ParsedPack, validate_pack

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(frozen=True, slots=True)
class IngestSource:
    """How the ingestor should stamp the new ``pack_source`` columns.

    ``builtin`` for the auto-applied built-in pack on first boot,
    ``community`` for operator uploads via the API.

    ``source_id`` optionally carries the ``pack_sources.id`` FK when
    the ingest is driven by a registered community source. It's used
    to :

      * stamp ``platform.pack_source_id`` on inserts / updates (row
        provenance),
      * look up ``platform_source_binding`` rows to filter skipped
        slugs before writing them.

    Left ``None`` for the legacy builtin and manual-upload flows —
    both proceed unchanged.
    """

    pack_source: str
    applied_by: str
    source_id: int | None = None


def _enforce_version_order(
    *, pack_version: str, snapshot: DBSnapshot, parsed_slugs: set[str]
) -> None:
    """FR-013a — reject incoming packs older than what's recorded for
    any of their slugs (excluding user-overridden rows).

    Comparison is lexical, which matches the ``YYYY.MM.NNN`` date order.
    """
    for slug in parsed_slugs:
        snap = snapshot.platforms_by_slug.get(slug)
        if snap is None or snap.pack_source == "user":
            continue
        if snap.pack_version is None:
            continue
        if pack_version < snap.pack_version:
            raise PackVersionConflictError(
                f"pack version {pack_version!r} is older than the "
                f"version recorded for slug {slug!r} "
                f"({snap.pack_version!r})"
            )


async def _insert_or_update_platforms(
    session: AsyncSession,
    *,
    parsed_platforms: list[dict[str, Any]],
    snapshot: DBSnapshot,
    source: IngestSource,
    pack_version: str,
) -> tuple[list[str], dict[str, int]]:
    """Apply per-platform rules. Returns (touched_slugs, slug→id map).

    The slug→id map is built post-flush so the parent-link patch pass
    can resolve ``parent_platform_slug`` to integer FKs.
    """
    touched: list[str] = []
    slug_to_id: dict[str, int] = {
        s: snap.id for s, snap in snapshot.platforms_by_slug.items()
    }

    # Migration 0043 — per-(source, slug) skip binding. Load once
    # per apply; empty set for the legacy source_id=None flows.
    skipped_slugs: set[str] = set()
    if source.source_id is not None:
        from romarr.platform_packs.models import PlatformSourceBinding

        skip_rows = (
            (
                await session.execute(
                    select(PlatformSourceBinding).where(
                        PlatformSourceBinding.source_id == source.source_id,
                        PlatformSourceBinding.mode == "skip",
                    )
                )
            )
            .scalars()
            .all()
        )
        skipped_slugs = {b.platform_slug for b in skip_rows}

    for plat in parsed_platforms:
        slug = plat["slug"]
        existing = snapshot.platforms_by_slug.get(slug)

        if existing is not None and existing.pack_source == "user":
            # FR-012: user wins. Skip the entire platform.
            continue

        if slug in skipped_slugs:
            # Operator flagged this (source, slug) as skip via the
            # Update Center — respect it silently.
            continue

        meta_ids = plat.get("metadata_ids") or {}

        if existing is None:
            # Insert new platform.
            new_platform = Platform(
                slug=slug,
                name=plat["name"],
                short_name=plat.get("short_name"),
                manufacturer=plat["manufacturer"],
                release_year=plat.get("release_year"),
                aliases=plat.get("aliases") or [],
                igdb_id=meta_ids.get("igdb_id"),
                screenscraper_id=meta_ids.get("screenscraper_id"),
                mobygames_id=meta_ids.get("mobygames_id"),
                launchbox_id=meta_ids.get("launchbox_id"),
                retroachievements_id=meta_ids.get("retroachievements_id"),
                pack_source=source.pack_source,
                pack_version=pack_version,
                pack_source_id=source.source_id,
            )
            session.add(new_platform)
            await session.flush()
            slug_to_id[slug] = new_platform.id
            touched.append(slug)
        else:
            # Update existing non-user-overridden platform.
            row = (
                await session.execute(
                    select(Platform).where(Platform.id == existing.id)
                )
            ).scalar_one()
            row.name = plat["name"]
            row.short_name = plat.get("short_name")
            row.manufacturer = plat["manufacturer"]
            row.release_year = plat.get("release_year")
            row.aliases = plat.get("aliases") or []
            row.igdb_id = meta_ids.get("igdb_id")
            row.screenscraper_id = meta_ids.get("screenscraper_id")
            row.mobygames_id = meta_ids.get("mobygames_id")
            row.launchbox_id = meta_ids.get("launchbox_id")
            row.retroachievements_id = meta_ids.get("retroachievements_id")
            row.pack_source = source.pack_source
            row.pack_version = pack_version
            row.pack_source_id = source.source_id
            touched.append(slug)

        # Apply formats: replace the full set for this platform.
        await _replace_formats(
            session,
            platform_id=slug_to_id[slug],
            formats=plat.get("formats") or [],
            source=source,
        )
        # Apply naming tokens: replace the full set for this platform.
        await _replace_naming_tokens(
            session,
            platform_id=slug_to_id[slug],
            tokens=plat.get("naming_tokens") or [],
            source=source,
        )

        # Migration 0044 — persist the per-(source, slug) snapshot
        # so the materializer can compose prefer + array-fusion
        # rules across every source that touches this platform.
        # Only for community ingest (source_id is None for legacy
        # builtin + manual-upload flows).
        if source.source_id is not None:
            from romarr.platform_packs.materialize import (
                _snapshot_platform,
                snapshot_contribution,
            )

            contribution = _snapshot_platform(
                plat,
                formats=list(plat.get("formats") or []),
                naming_tokens=list(plat.get("naming_tokens") or []),
            )
            await snapshot_contribution(
                session,
                source_id=source.source_id,
                platform_slug=slug,
                contribution=contribution,
                pack_version=pack_version,
            )

    return touched, slug_to_id


async def _replace_formats(
    session: AsyncSession,
    *,
    platform_id: int,
    formats: list[dict[str, Any]],
    source: IngestSource,
) -> None:
    """Delete every existing format on ``platform_id`` and re-insert
    from the pack. The cascade on PlatformFormat already cleans up,
    but a DELETE + INSERT keeps the apply path predictable."""
    await session.execute(
        delete(PlatformFormat).where(PlatformFormat.platform_id == platform_id)
    )
    for fmt in formats:
        session.add(
            PlatformFormat(
                platform_id=platform_id,
                extension=fmt["extension"],
                format_type=fmt["format_type"],
                pack_source=source.pack_source,
            )
        )


async def _replace_naming_tokens(
    session: AsyncSession,
    *,
    platform_id: int,
    tokens: list[dict[str, Any]],
    source: IngestSource,
) -> None:
    await session.execute(
        delete(PlatformNamingToken).where(
            PlatformNamingToken.platform_id == platform_id
        )
    )
    for idx, tok in enumerate(tokens):
        # The pack format doesn't expose a per-token name; derive a
        # deterministic one from the meaning + index so the unique
        # constraint on (platform_id, name) holds.
        name = f"{tok['meaning']}-{idx}"
        session.add(
            PlatformNamingToken(
                platform_id=platform_id,
                name=name,
                pattern=tok["pattern"],
                meaning=tok["meaning"],
                pack_source=source.pack_source,
            )
        )


async def _patch_parent_links(
    session: AsyncSession,
    *,
    parsed_platforms: list[dict[str, Any]],
    slug_to_id: dict[str, int],
    snapshot: DBSnapshot,
) -> None:
    """Resolve parent_platform_slug → parent_platform_id post-insert.

    Skips user-overridden platforms (their parent link is the
    operator's call). The slug → id map covers both newly-inserted
    rows and pre-existing ones from the snapshot.
    """
    for plat in parsed_platforms:
        slug = plat["slug"]
        existing = snapshot.platforms_by_slug.get(slug)
        if existing is not None and existing.pack_source == "user":
            continue
        target_slug = plat.get("parent_platform_slug")
        target_id = slug_to_id.get(target_slug) if target_slug else None
        platform_id = slug_to_id.get(slug)
        if platform_id is None:
            continue
        row = (
            await session.execute(
                select(Platform).where(Platform.id == platform_id)
            )
        ).scalar_one()
        row.parent_platform_id = target_id


async def _apply_parsing_strategies(
    session: AsyncSession,
    *,
    parsed: dict[str, Any],
    snapshot: DBSnapshot,
    source: IngestSource,
    pack_version: str,
) -> list[str]:
    """Upsert each parsing strategy, skipping user-overridden ones."""
    touched: list[str] = []
    for strategy in parsed.get("parsing_strategies") or []:
        sid = strategy["id"]
        existing = snapshot.strategies_by_id.get(sid)
        if existing is not None and existing.pack_source == "user":
            continue
        await session.execute(
            delete(ParsingStrategy).where(ParsingStrategy.id == sid)
        )
        session.add(
            ParsingStrategy(
                id=sid,
                name=strategy.get("description") or sid,
                pattern=strategy["regex"],
                apply_to_platforms=list(strategy.get("apply_to_platforms") or []),
                pack_version=pack_version,
                pack_source=source.pack_source,
            )
        )
        touched.append(sid)
    return touched


async def _insert_platform_pack_row(
    session: AsyncSession,
    *,
    parsed: ParsedPack,
    source: IngestSource,
) -> None:
    body = parsed.parsed
    session.add(
        PlatformPack(
            pack_version=parsed.pack_version,
            schema_version=int(body.get("schema_version", 1)),
            description=body.get("description"),
            author=body.get("author"),
            source_url=body.get("source_url"),
            contents_hash=parsed.contents_hash,
            pack_source=source.pack_source,
            applied_at=datetime.now(UTC),
            applied_by=source.applied_by,
        )
    )
    await session.flush()


async def _record_skipped(
    session: AsyncSession,
    *,
    parsed: ParsedPack,
    source: IngestSource,
    diff: list[PackPlatformDiff],
) -> PackUploadResult:
    """Idempotent re-apply: pack_version + hash already present."""
    started = datetime.now(UTC)
    log = await start_log(
        session,
        pack_version=parsed.pack_version,
        applied_by=source.applied_by,
    )
    await complete_log(
        session,
        log,
        action="skipped",
        platforms_affected=[],
        parsing_strategies_affected=[],
    )
    await session.commit()
    return PackUploadResult(
        pack_version=parsed.pack_version,
        contents_hash=parsed.contents_hash,
        action="skipped",
        diff=diff,
        parsing_strategies_affected=[],
        started_at=started,
        finished_at=datetime.now(UTC),
    )


async def ingest_pack(
    session: AsyncSession,
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    content: bytes,
    source: IngestSource,
) -> PackUploadResult:
    """Top-level entry point: validate → snapshot → diff → transactional apply.

    ``sessionmaker`` is required so that on failure the audit-log
    row can be persisted in a fresh session, independent of the
    rolled-back ingestor transaction.
    """
    snapshot = await load_snapshot(session)
    existing_slugs = set(snapshot.platforms_by_slug)

    parsed = validate_pack(content, existing_slugs=existing_slugs)
    parsed_platforms = parsed.parsed.get("platforms") or []

    # FR-009: same (version, hash) → idempotent skip without touching state.
    existing_pack = (
        await session.execute(
            select(PlatformPack).where(
                PlatformPack.pack_version == parsed.pack_version
            )
        )
    ).scalar_one_or_none()
    if existing_pack is not None:
        if existing_pack.contents_hash == parsed.contents_hash:
            diff = compute_platform_diff(parsed_platforms, snapshot)
            return await _record_skipped(
                session, parsed=parsed, source=source, diff=diff
            )
        # The 0001 migration seeds a placeholder ``platform_pack``
        # row with ``contents_hash = "0" * 64`` so the FK target
        # exists for the seeded ``platform_format`` rows. The real
        # built-in pack first-boot apply lands the actual hash —
        # treat the placeholder sentinel as "no pack yet" and
        # delete it here so the regular insert path runs below.
        if existing_pack.contents_hash == "0" * 64:
            await session.delete(existing_pack)
            await session.flush()
            existing_pack = None
        else:
            # FR-010: same version, different hash → conflict.
            raise PackVersionConflictError(parsed.pack_version)

    # FR-013a: reject downgrades by lexical pack_version order.
    _enforce_version_order(
        pack_version=parsed.pack_version,
        snapshot=snapshot,
        parsed_slugs={p["slug"] for p in parsed_platforms},
    )

    diff = compute_platform_diff(parsed_platforms, snapshot)
    started = datetime.now(UTC)

    try:
        log = await start_log(
            session,
            pack_version=parsed.pack_version,
            applied_by=source.applied_by,
        )

        touched_platforms, slug_to_id = await _insert_or_update_platforms(
            session,
            parsed_platforms=parsed_platforms,
            snapshot=snapshot,
            source=source,
            pack_version=parsed.pack_version,
        )
        await _patch_parent_links(
            session,
            parsed_platforms=parsed_platforms,
            slug_to_id=slug_to_id,
            snapshot=snapshot,
        )
        touched_strategies = await _apply_parsing_strategies(
            session,
            parsed=parsed.parsed,
            snapshot=snapshot,
            source=source,
            pack_version=parsed.pack_version,
        )
        await _insert_platform_pack_row(session, parsed=parsed, source=source)

        action = "applied"
        await complete_log(
            session,
            log,
            action=action,
            platforms_affected=touched_platforms,
            parsing_strategies_affected=touched_strategies,
        )

        # Migration 0044 — after every community ingest, rebuild
        # the live Platform row for each touched slug from the
        # stack of snapshotted contributions. Honours prefer
        # bindings + unions arrays across sources. No-op for
        # non-community ingest (source_id is None).
        if source.source_id is not None and touched_platforms:
            from romarr.platform_packs.materialize import (
                materialize_all_slugs,
            )

            await materialize_all_slugs(
                session, slugs=list(touched_platforms)
            )

        await session.commit()
    except Exception as exc:
        await session.rollback()
        await fail_log(
            sessionmaker,
            pack_version=parsed.pack_version,
            applied_by=source.applied_by,
            started_at=started,
            error_message=str(exc),
        )
        raise

    return PackUploadResult(
        pack_version=parsed.pack_version,
        contents_hash=parsed.contents_hash,
        action=action,
        diff=diff,
        parsing_strategies_affected=touched_strategies,
        started_at=started,
        finished_at=datetime.now(UTC),
    )


__all__ = [
    "IngestSource",
    "ingest_pack",
]
