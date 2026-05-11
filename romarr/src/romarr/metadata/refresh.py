"""Per-Game metadata refresh orchestrator (T055).

Wires the cached provider responses → pure :func:`aggregate` → Game
persistence path. The orchestrator:

  1. Acquires a per-Game asyncio lock so concurrent calls coalesce
     (FR-013a). Cross-process coalescing via Redis is out of scope at
     MVP — the locks live in the orchestrator's process memory.
  2. Loads enabled, scan-flow providers via :func:`load_enabled_providers`.
  3. For each provider, hits the cache; on miss / expiry / ``force``,
     issues a ``search_games + get_game`` round and persists the
     provider's full payload via :func:`put_cached`.
  4. Calls the pure :func:`aggregate` with the cached corpus +
     field-priority table + Game's current state.
  5. Applies the result to the Game (non-locked fields only) and
     stamps ``needs_metadata_refresh``.
  6. If aggregation picked a cover URL, fetches the bytes via the
     winning provider's ``get_cover`` and writes them to disk via
     :func:`write_cover`; ``Game.cover_path`` is updated atomically.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from romarr.config.settings import get_settings
from romarr.domain.models import Game, Platform
from romarr.metadata.aggregator import aggregate
from romarr.metadata.cache import get_cached, put_cached
from romarr.metadata.covers import (
    UnsupportedCoverContentTypeError,
    write_cover,
)
from romarr.metadata.errors import NotFoundError, ProviderError
from romarr.metadata.models import (
    FieldPriority,
    MetadataCache,
    MetadataProviderConfig,
)
from romarr.metadata.registry import load_enabled_providers
from romarr.metadata.types import AggregationResult, GameMetadata, ProviderField

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.metadata.providers.base import MetadataProvider

logger = logging.getLogger(__name__)

# Per-Game advisory lock registry. ``asyncio.Lock`` instances are
# created on demand and recycled while a refresh is in flight.
# Process-local; FR-013a's "cross-process coalescing via Redis" is
# documented as deferred-to-v1.
_GAME_LOCKS: dict[int, asyncio.Lock] = {}


# Slice 388 — provider canonical name → Game ORM column that
# stores its primary id. Mirrors the LookupAdd table in
# ``romarr.metadata.api.lookup`` so the refresh path honours the
# same FK contract the add path writes.
_PROVIDER_FK_COLUMN: dict[str, str] = {
    "igdb": "igdb_id",
    "mobygames": "mobygames_id",
    "screenscraper": "screenscraper_id",
    "launchbox": "launchbox_id",
    "retroachievements": "retroachievements_id",
}


def _pinned_provider_id(game: Game, provider_name: str) -> str | None:
    """Return the provider FK on ``game`` as a string, or None.

    The lookup-add endpoint pins the chosen provider's id on the
    matching FK column (igdb_id / mobygames_id / …). When that FK
    is set we trust it: the refresh calls ``get_game(pinned)``
    directly instead of re-running ``search_games(title)`` which
    can stop on a title-collision sibling and overwrite the
    operator's pick.
    """
    column = _PROVIDER_FK_COLUMN.get(provider_name.lower())
    if column is None:
        return None
    raw = getattr(game, column, None)
    return str(raw) if raw is not None else None


def _lock_for(game_id: int) -> asyncio.Lock:
    lock = _GAME_LOCKS.get(game_id)
    if lock is None:
        lock = asyncio.Lock()
        _GAME_LOCKS[game_id] = lock
    return lock


async def _load_field_priority(
    session: AsyncSession,
) -> list[tuple[str, int, str]]:
    rows = (
        await session.execute(
            select(
                FieldPriority.field_name,
                FieldPriority.priority_order,
                FieldPriority.provider_name,
            )
        )
    ).all()
    return [(r[0], r[1], r[2]) for r in rows]


def _existing_from_game(game: Game) -> dict[ProviderField, Any]:
    """Project the Game's current persisted state into ProviderField keys."""
    return {
        ProviderField.TITLE: game.title,
        ProviderField.SUMMARY: game.summary,
        ProviderField.COVER: game.cover_path,
        ProviderField.GENRES: list(game.genres),
        ProviderField.RELEASE_DATE: game.release_date,
        ProviderField.DEVELOPER: game.developer,
        ProviderField.PUBLISHER: game.publisher,
        ProviderField.RATING: game.rating,
        ProviderField.AGE_RATING: game.age_rating,
        ProviderField.THEMES: list(game.themes),
        ProviderField.FRANCHISES: list(game.franchises),
        ProviderField.PLAYERS_MIN: game.players_min,
        ProviderField.PLAYERS_MAX: game.players_max,
        ProviderField.HLTB_MAIN: game.hltb_main,
        ProviderField.ACHIEVEMENTS_COUNT: game.achievements_count,
    }


def _apply_to_game(game: Game, result: AggregationResult) -> None:
    """Persist aggregator output onto the Game.

    Locked fields are reported in ``result.skipped_locked``; the
    aggregator already withheld them from ``result.fields`` so this
    pass touches no locked column. Provider-name tuples are flattened
    to scalar field assignments here.
    """
    for field, (value, _winner) in result.fields.items():
        if field == ProviderField.TITLE:
            game.title = value
        elif field == ProviderField.SUMMARY:
            game.summary = value
        elif field == ProviderField.COVER:
            # Cover_path is set by the cover-fetch path below; keep
            # the raw URL out of the DB row so the API never leaks
            # third-party CDN URLs.
            pass
        elif field == ProviderField.GENRES:
            game.genres = list(value)
        elif field == ProviderField.RELEASE_DATE:
            game.release_date = value
        elif field == ProviderField.DEVELOPER:
            game.developer = value
        elif field == ProviderField.PUBLISHER:
            game.publisher = value
        elif field == ProviderField.RATING:
            game.rating = float(value)
        elif field == ProviderField.AGE_RATING:
            game.age_rating = value
        elif field == ProviderField.THEMES:
            game.themes = list(value)
        elif field == ProviderField.FRANCHISES:
            game.franchises = list(value)
        elif field == ProviderField.PLAYERS_MIN:
            game.players_min = int(value)
        elif field == ProviderField.PLAYERS_MAX:
            game.players_max = int(value)
        elif field == ProviderField.HLTB_MAIN:
            game.hltb_main = int(value)
        elif field == ProviderField.ACHIEVEMENTS_COUNT:
            game.achievements_count = int(value)

    game.needs_metadata_refresh = result.needs_metadata_refresh


async def _ensure_provider_payload(
    session: AsyncSession,
    *,
    game: Game,
    platform_slug: str | None,
    provider: MetadataProvider,
    force: bool,
) -> GameMetadata | None:
    """Return the provider's payload for ``game``.

    Cache hit (and not ``force``) → return the cached
    :class:`GameMetadata`. Otherwise issue a search → get_game and
    persist the fresh payload. Provider-side failures (auth, transient,
    rate-limit) are caught and logged so a single bad provider doesn't
    poison the pipeline (FR-016 / US4).
    """
    if not force:
        row = await get_cached(
            session, provider_name=provider.name, game_id=game.id
        )
        if row is not None:
            return _meta_from_cache_row(provider, row)

    # Slice 388 — when the Game already carries the provider's FK
    # (because it was added from a lookup candidate that pinned
    # the id), trust it and call ``get_game`` directly. Re-running
    # ``search_games(title)`` and grabbing ``candidates[0]`` is a
    # title-collision footgun: searching IGDB for "Sonic Advance"
    # often returns "Combo Pack: Sonic Advance + Sonic Pinball
    # Party" first, which then overwrites the operator's pick.
    pinned_id = _pinned_provider_id(game, provider.name)
    try:
        if pinned_id is not None:
            meta = await provider.get_game(pinned_id)
        else:
            candidates = await provider.search_games(
                game.title, platform_slug=platform_slug
            )
            if not candidates:
                logger.info(
                    "metadata.refresh.no_match", extra={"provider": provider.name}
                )
                return None
            provider_game_id = candidates[0].provider_game_id
            meta = await provider.get_game(provider_game_id)
    except NotFoundError:
        return None
    except NotImplementedError:
        # Cover-only providers (SteamGridDB) intentionally don't
        # implement search/get_game. They're already filtered from
        # the scan flow by ``invoked_in_scan=False`` but we guard
        # against a misconfigured ``scan=False`` invocation too.
        return None
    except ProviderError as exc:
        logger.warning(
            "metadata.refresh.provider_error",
            extra={"provider": provider.name, "err": str(exc)},
        )
        return None

    # Persist a normalized payload so future cache hits can rebuild the
    # GameMetadata without re-running the provider's parsing logic.
    payload = _meta_to_payload(meta)
    await put_cached(
        session,
        provider_name=provider.name,
        provider_game_id=meta.provider_game_id,
        game_id=game.id,
        data=payload,
        ttl_seconds=await _ttl_for(session, provider.name),
    )
    return meta


async def _ttl_for(session: AsyncSession, provider_name: str) -> int:
    row = (
        await session.execute(
            select(MetadataProviderConfig.cache_ttl_seconds).where(
                MetadataProviderConfig.provider_name == provider_name
            )
        )
    ).scalar_one_or_none()
    return int(row or 2_592_000)


def _meta_to_payload(meta: GameMetadata) -> dict[str, Any]:
    """Serialize a :class:`GameMetadata` into the cache JSON shape.

    ``ProviderField`` keys round-trip as their string values;
    :class:`datetime` values become ISO-8601 strings so SQLite's
    :class:`sqlalchemy.JSON` column doesn't choke on them.
    """
    encoded: dict[str, Any] = {}
    for field, value in meta.fields.items():
        if isinstance(value, datetime):
            encoded[field.value] = {"__datetime__": value.isoformat()}
        else:
            encoded[field.value] = value
    return {
        "provider_name": meta.provider_name,
        "provider_game_id": meta.provider_game_id,
        "fields": encoded,
        "cover_url": meta.cover_url,
        "fetched_at": meta.fetched_at.isoformat(),
    }


def _payload_to_meta(payload: dict[str, Any]) -> GameMetadata:
    fields: dict[ProviderField, Any] = {}
    for k, v in (payload.get("fields") or {}).items():
        if isinstance(v, dict) and "__datetime__" in v:
            fields[ProviderField(k)] = datetime.fromisoformat(v["__datetime__"])
        else:
            fields[ProviderField(k)] = v
    return GameMetadata(
        provider_name=payload["provider_name"],
        provider_game_id=payload["provider_game_id"],
        fields=fields,
        cover_url=payload.get("cover_url"),
        fetched_at=datetime.fromisoformat(payload["fetched_at"]),
    )


def _meta_from_cache_row(
    provider: MetadataProvider, row: MetadataCache
) -> GameMetadata:
    return _payload_to_meta(dict(row.data))


async def _maybe_persist_cover(
    *,
    game: Game,
    cached: dict[str, GameMetadata],
    providers_by_name: dict[str, MetadataProvider],
    result: AggregationResult,
) -> None:
    """If aggregation picked a cover URL, fetch + write it to disk."""
    cover_entry = result.fields.get(ProviderField.COVER)
    if cover_entry is None:
        return
    _, winner_name = cover_entry
    if winner_name in {"<locked>", "<existing>"}:
        return
    provider = providers_by_name.get(winner_name)
    if provider is None:
        return
    meta = cached.get(winner_name)
    if meta is None or not meta.cover_url:
        return
    try:
        data, content_type = await provider.get_cover(meta.provider_game_id)
    except (NotFoundError, ProviderError, NotImplementedError):
        # Providers that only contribute non-cover fields (RA, HLTB)
        # raise NotImplementedError on get_cover. The aggregator will
        # not normally pick them as cover winners — but if a custom
        # field_priority does, we degrade gracefully rather than crash.
        logger.warning("metadata.refresh.cover_fetch_failed")
        return
    try:
        path = write_cover(game.id, content_type=content_type, data=data)
    except UnsupportedCoverContentTypeError:
        logger.warning(
            "metadata.refresh.cover_unsupported_type",
            extra={"content_type": content_type},
        )
        return
    game.cover_path = str(path)


async def refresh_game_metadata(
    session: AsyncSession,
    *,
    game_id: int,
    force: bool = False,
) -> AggregationResult:
    """Refresh metadata for a single Game; returns the aggregation result.

    Concurrent calls with the same ``game_id`` coalesce on the
    in-process per-Game lock (FR-013a). Provider quota is burned
    exactly once per concurrent burst.
    """
    lock = _lock_for(game_id)
    async with lock:
        return await _refresh_inner(session, game_id=game_id, force=force)


async def _resolve_provider_ids_via_hash(
    session: AsyncSession, *, game: Game
) -> None:
    """Slice 414 — use Hasheous to populate missing provider FK
    columns on ``game`` from the file hash of any imported Dump.

    Hasheous is a hash-keyed cross-reference service: given a
    SHA-1 / MD5 / CRC, it returns the corresponding IGDB,
    RetroAchievements, TheGamesDB and MobyGames immutable IDs.
    We only write FK columns that are currently NULL — the
    operator's manual pin (or a previous Hasheous lookup) wins.

    Failure modes are all silent: Hasheous unreachable, hash
    unknown, no Dump rows yet. The per-provider refresh loop
    handles the no-id case by falling back to title search.
    """
    from romarr.domain.models import Dump, Release
    from romarr.identification.hashmatch.remote import HasheousBackend

    # Pick the first Dump with at least one hash. The Hasheous
    # ``ByHash`` endpoint accepts any of (md5, sha1, crc) so a
    # single Dump is enough.
    dump_row = (
        await session.execute(
            select(Dump.sha1, Dump.md5, Dump.crc32)
            .join(Release, Release.id == Dump.release_id)
            .where(Release.game_id == game.id)
            .limit(1)
        )
    ).one_or_none()
    if dump_row is None:
        return
    sha1, md5, crc32 = dump_row
    if not (sha1 or md5 or crc32):
        return

    try:
        backend = HasheousBackend(get_settings())
    except Exception:
        return
    try:
        refs = await backend.lookup_cross_refs(
            sha1=sha1, md5=md5, crc32=crc32
        )
    except Exception:
        logger.exception("metadata.refresh.hasheous_lookup_failed")
        return
    if not refs:
        return

    # Provider FK column on Game keyed by Romarr's metadata
    # provider name. Mirrors ``_PROVIDER_FK_COLUMN`` in
    # ``lookup.py`` so the refresh path and the lookup-add path
    # write the same columns.
    column_by_provider = {
        "igdb": "igdb_id",
        "mobygames": "mobygames_id",
        "retroachievements": "retroachievements_id",
    }
    populated: list[str] = []
    for provider_name, column in column_by_provider.items():
        existing = getattr(game, column, None)
        if existing is not None:
            continue  # operator pin / prior lookup wins
        raw = refs.get(provider_name)
        if raw is None:
            continue
        try:
            setattr(game, column, int(raw))
            populated.append(provider_name)
        except (TypeError, ValueError):
            continue
    if populated:
        await session.flush()
        logger.info(
            "metadata.refresh.hasheous_cross_refs_pinned",
            extra={"game_id": game.id, "providers": populated},
        )


async def _refresh_inner(
    session: AsyncSession, *, game_id: int, force: bool
) -> AggregationResult:
    game = (
        await session.execute(select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    if game is None:
        raise ValueError(f"game {game_id} not found")

    platform = (
        await session.execute(
            select(Platform).where(Platform.id == game.platform_id)
        )
    ).scalar_one_or_none()
    platform_slug = platform.slug if platform is not None else None

    # Slice 414 — RomM-style hash-driven cross-reference. If
    # this game has at least one Dump on disk and Hasheous is
    # enabled, look up the hash and pin any missing per-
    # provider FK column on the Game. The per-provider refresh
    # loop below then calls ``get_game(pinned_id)`` directly —
    # no more fuzzy title matching against ``Disney's Tarzan``
    # / ``Tom Clancy's …`` / publisher-prefix variants.
    await _resolve_provider_ids_via_hash(session, game=game)

    providers = await load_enabled_providers(session, scan=True)
    providers_by_name = {p.name: p for p in providers}

    cached: dict[str, GameMetadata] = {}
    for provider in providers:
        meta = await _ensure_provider_payload(
            session,
            game=game,
            platform_slug=platform_slug,
            provider=provider,
            force=force,
        )
        if meta is not None:
            cached[provider.name] = meta

    field_priority = await _load_field_priority(session)
    locked = list(game.locked_fields or [])
    existing = _existing_from_game(game)

    result = aggregate(
        game_id=game.id,
        locked_fields=locked,
        cached=cached,
        field_priority=field_priority,
        existing=existing,
    )

    _apply_to_game(game, result)
    await _maybe_persist_cover(
        game=game,
        cached=cached,
        providers_by_name=providers_by_name,
        result=result,
    )
    await session.commit()
    await session.refresh(game)
    return result
