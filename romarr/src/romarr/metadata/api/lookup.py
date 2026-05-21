"""Operator-facing metadata lookup endpoints.

  - GET  /api/v3/game/lookup?q=...&platform_slug=...
  - POST /api/v3/game/lookup/add

The GET wraps :meth:`MetadataProvider.search_games` across every
enabled provider, collates the results, and returns the union
ranked by per-result confidence. The Frontend AddNew page consumes
this to surface candidates the operator can add to the Library.

The POST instantiates a :class:`Game` row from one chosen lookup
candidate. The metadata aggregator then enriches the rest of the
fields asynchronously via the ``needs_metadata_refresh`` flag —
this endpoint only persists the bare minimum (title + platform +
provider FK) so the Game appears in the Library immediately.

Network failures from any single provider during the GET are
caught and dropped from the response — partial results are better
than no results when the operator is mid-search.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, get_event_channel, require_admin
from romarr.auth import Principal
from romarr.domain.models import Game, Platform
from romarr.domain.schemas import GameRead
from romarr.metadata.providers import MetadataProvider
from romarr.metadata.registry import load_enabled_providers
from romarr.metadata.types import GameSearchResult
from romarr.notifications.channel import EventChannel
from romarr.notifications.types import GameRef, OnGameAddedPayload

router = APIRouter(prefix="/api/v3/game", tags=["Metadata"])

# Map provider canonical name → Game ORM column that stores its id.
# Only providers that contribute primary identification metadata
# get a dedicated FK column. Auxiliary providers (covers, hashes,
# achievements, durations, hash-match proxies) are not represented
# here — adding via those names returns 400.
_PROVIDER_TO_FK_COLUMN: dict[str, str] = {
    "igdb": "igdb_id",
    "mobygames": "mobygames_id",
    "screenscraper": "screenscraper_id",
    "launchbox": "launchbox_id",
    "retroachievements": "retroachievements_id",
}

# Slug normalisation: strip diacritics by replacing common Latin
# accented vowels with their ASCII counterpart, then collapse any
# non-[a-z0-9] run into a single hyphen and trim leading/trailing
# hyphens. We don't pull in a third-party slugify dep — the rule
# matches :data:`romarr.domain.validators.SLUG_PATTERN` and the
# corner cases (empty result, all-symbol titles) fall back to a
# canonical placeholder ``untitled``.
_DIACRITIC_FOLD = str.maketrans(
    "àáâãäåçèéêëìíîïñòóôõöøùúûüýÿÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝŸ",
    "aaaaaaceeeeiiiinoooooouuuuyyAAAAAACEEEEIIIINOOOOOOUUUUYY",
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_title(title: str) -> str:
    """Convert a free-form title to a kebab-case slug.

    The resulting slug satisfies
    :data:`romarr.domain.validators.SLUG_PATTERN`. Empty / pure-
    symbol titles fall back to ``untitled`` so the row is still
    persistable; the operator can rename later.
    """
    folded = title.lower().translate(_DIACRITIC_FOLD)
    cleaned = _SLUG_RE.sub("-", folded).strip("-")
    if not cleaned:
        return "untitled"
    return cleaned[:192]


_DEDUPE_KEY_PUNCT = re.compile(r"[^a-z0-9]+")


def _dedupe_key(r: GameSearchResult) -> tuple[str, int | None, str | None]:
    """Slice 410 — group key for cross-provider dedupe.

    Title is normalised (lower + strip punctuation, first 40
    chars) so "Sonic the Hedgehog" / "sonic-the-hedgehog" /
    "Sonic_the_Hedgehog" all collapse. The platform slug + year
    finish disambiguating: same title on a different console
    (NES Metroid vs SNES Super Metroid) stays separate.
    """
    title = _DEDUPE_KEY_PUNCT.sub("", r.title.lower())
    return (title[:40], r.release_year, r.platform_slug)


def _dedupe_across_providers(
    results: list[GameSearchResult],
) -> list[tuple[GameSearchResult, list[GameSearchResult]]]:
    """Collapse same-game-across-providers into one canonical
    :class:`GameSearchResult` per group, with the per-group list
    of every provider hit (canonical included) attached.

    Input must be sorted by ``confidence`` desc; the first row
    in each group wins as the canonical hit. Returns
    ``[(canonical, [hit1, hit2, ...]), ...]`` preserving the
    confidence-desc order across groups.
    """
    seen: dict[tuple[str, int | None, str | None], int] = {}
    groups: list[list[GameSearchResult]] = []
    for r in results:
        key = _dedupe_key(r)
        idx = seen.get(key)
        if idx is None:
            seen[key] = len(groups)
            groups.append([r])
        else:
            groups[idx].append(r)
    return [(group[0], group) for group in groups]


async def _allocate_unique_slug(
    db: AsyncSession, *, platform_id: int, base: str
) -> str:
    """Return a slug that's free under ``(platform_id, slug)``.

    Appends ``-2``, ``-3`` … until the unique constraint clears.
    The 192-char domain ceiling is respected by truncating the
    base before appending the disambiguation suffix.
    """
    candidate = base
    suffix = 2
    while True:
        existing = await db.execute(
            select(Game.id).where(
                Game.platform_id == platform_id, Game.slug == candidate
            )
        )
        if existing.scalar_one_or_none() is None:
            return candidate
        marker = f"-{suffix}"
        candidate = f"{base[: 192 - len(marker)]}{marker}"
        suffix += 1


class ProviderHit(BaseModel):
    """Slice 410 — one (provider, provider_game_id) pair carried
    by a deduped lookup row. The same game returned by multiple
    providers collapses into one ``GameLookupRow`` whose
    ``providers`` list enumerates every provider that found it.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    game_id: str = Field(alias="gameId")
    confidence: float


class GameLookupRow(BaseModel):
    """One row in the lookup response — a deduped game.

    Slice 410 — when the same game shows up in multiple
    providers (IGDB + ScreenScraper + MobyGames…), they merge
    into a single row whose ``providers`` list carries every
    provider that returned it. The canonical ``providerName`` /
    ``providerGameId`` point at the highest-confidence hit so
    the one-click Add path stays unambiguous.
    """

    model_config = ConfigDict(
        extra="forbid", from_attributes=True, populate_by_name=True
    )

    rank: int
    provider_name: str = Field(alias="providerName")
    provider_game_id: str = Field(alias="providerGameId")
    title: str
    confidence: float
    platform_slug: str | None = Field(default=None, alias="platformSlug")
    platform_name: str | None = Field(default=None, alias="platformName")
    platform_manufacturer: str | None = Field(
        default=None, alias="platformManufacturer"
    )
    release_year: int | None = Field(default=None, alias="releaseYear")
    cover_url: str | None = Field(default=None, alias="coverUrl")
    providers: list[ProviderHit] = Field(default_factory=list)


@router.get(
    "/lookup",
    response_model=list[GameLookupRow],
    response_model_by_alias=True,
    summary=(
        "Search every enabled metadata provider for games matching "
        "the query. Returns the merged candidate list ranked by "
        "confidence (admin only)."
    ),
)
async def lookup_games(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[
        str,
        Query(
            description="Title substring to look up.",
            min_length=1,
            max_length=255,
        ),
    ],
    platform_slug: Annotated[
        str | None,
        Query(
            alias="platformSlug",
            description=(
                "Optional platform slug filter — providers that "
                "honour platform mapping use it to scope results."
            ),
            max_length=64,
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[GameLookupRow]:
    if not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "query is required",
                "errorCode": "invalid_query",
            },
        )

    providers: list[MetadataProvider] = await load_enabled_providers(
        db, scan=False
    )

    merged: list[GameSearchResult] = []
    for provider in providers:
        try:
            results = await provider.search_games(
                q.strip(), platform_slug=platform_slug
            )
        except Exception:
            # Defensive: a single provider failure shouldn't sink
            # the whole lookup. The operator gets partial results
            # and the affected provider's failure surfaces in the
            # health panel.
            continue
        merged.extend(results)

    merged.sort(key=lambda r: r.confidence, reverse=True)

    # Slice 410 — dedupe across providers. The same game often
    # appears in IGDB + ScreenScraper + MobyGames; collapsing
    # those into one row + tagging the providers cuts noise in
    # the AddNew list and gives the operator a clear "this hit
    # is corroborated by N sources" signal.
    deduped_groups = _dedupe_across_providers(merged)
    truncated_groups = deduped_groups[:limit]
    truncated = [canonical for canonical, _ in truncated_groups]
    hits_by_index: dict[int, list[GameSearchResult]] = {
        i: hits for i, (_, hits) in enumerate(truncated_groups)
    }

    # Enrich platform_name + manufacturer from the Platform table
    # for any row that carries a Romarr slug. Single bulk SELECT
    # keeps it cheap. When the slug isn't in the operator's
    # configured Platform table, we fall back to the
    # provider-supplied platform_name (e.g. IGDB's display name)
    # so the row still surfaces context.
    slugs_needed = {r.platform_slug for r in truncated if r.platform_slug}
    enrichment_by_slug: dict[str, tuple[str, str | None]] = {}
    if slugs_needed:
        rows_p = (
            await db.execute(
                select(Platform.slug, Platform.name, Platform.manufacturer).where(
                    Platform.slug.in_(slugs_needed)
                )
            )
        ).all()
        enrichment_by_slug = {
            slug: (name, manufacturer)
            for slug, name, manufacturer in rows_p
        }

    out_rows: list[GameLookupRow] = []
    for index, row in enumerate(truncated):
        # Romarr-side enrichment wins over provider-supplied names
        # so the operator sees their own naming convention. When
        # the slug isn't configured locally, fall back to the
        # provider name (e.g. IGDB's "Linux" / "Game & Watch").
        local_enrichment = (
            enrichment_by_slug.get(row.platform_slug)
            if row.platform_slug
            else None
        )
        if local_enrichment is not None:
            display_name, manufacturer = local_enrichment
        else:
            display_name = row.platform_name
            manufacturer = None
        hits = hits_by_index.get(index, [row])
        # Slice 412 — collapse same-provider hits inside a group
        # so the badge stack reads as the set of providers that
        # found this game (one badge per provider), not the raw
        # list of every hit. The aggregator picked the
        # highest-confidence hit as canonical already; for the
        # other providers we keep their best hit too.
        best_by_provider: dict[str, GameSearchResult] = {}
        for h in hits:
            existing = best_by_provider.get(h.provider_name)
            if existing is None or h.confidence > existing.confidence:
                best_by_provider[h.provider_name] = h
        providers = [
            ProviderHit(
                name=h.provider_name,
                gameId=h.provider_game_id,
                confidence=h.confidence,
            )
            for h in best_by_provider.values()
        ]
        out_rows.append(
            GameLookupRow(
                rank=index,
                providerName=row.provider_name,
                providerGameId=row.provider_game_id,
                title=row.title,
                confidence=row.confidence,
                platformSlug=(
                    row.platform_slug
                    if row.platform_slug in enrichment_by_slug
                    else None
                ),
                platformName=display_name,
                platformManufacturer=manufacturer,
                releaseYear=row.release_year,
                coverUrl=row.cover_url,
                providers=providers,
            )
        )
    return out_rows


class LookupAddRequest(BaseModel):
    """POST body for ``/api/v3/game/lookup/add``.

    The ``providerName`` + ``providerGameId`` pair identifies the
    chosen candidate from the GET response; everything else is
    operator input from the Add modal.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provider_name: Annotated[
        str, Field(alias="providerName", min_length=1, max_length=64)
    ]
    provider_game_id: Annotated[
        str, Field(alias="providerGameId", min_length=1, max_length=64)
    ]
    title: Annotated[str, Field(min_length=1, max_length=255)]
    platform_id: Annotated[int, Field(alias="platformId", ge=1)]
    # Slice 385 — Sonarr-style library binding. Optional so an
    # operator-less first-run / scripted add still works (the
    # importer falls back to platform routing); the AddGame UI
    # always sends it explicitly.
    library_id: Annotated[int | None, Field(alias="libraryId", ge=1)] = None
    monitored: bool = True


@router.post(
    "/lookup/add",
    response_model=GameRead,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Add a Game to the Library from a lookup candidate. "
        "The metadata aggregator enriches the rest of the fields "
        "asynchronously via the ``needs_metadata_refresh`` flag "
        "(admin only)."
    ),
)
async def add_game_from_lookup(
    body: Annotated[LookupAddRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    event_channel: Annotated[EventChannel | None, Depends(get_event_channel)] = None,
) -> GameRead:
    column = _PROVIDER_TO_FK_COLUMN.get(body.provider_name.lower())
    if column is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": (
                    f"provider_name={body.provider_name!r} is not a primary "
                    "metadata provider — Library adds require igdb, "
                    "mobygames, screenscraper, launchbox, or retroachievements."
                ),
                "errorCode": "unsupported_provider",
            },
        )

    # The lookup row carries the provider id as a string for
    # generality. The Game ORM stores integer FKs, so the conversion
    # has to happen here. A non-numeric id from a provider that
    # ought to use integers is a contract violation we surface as
    # 400 rather than letting it 500 in SQLAlchemy.
    try:
        provider_pk = int(body.provider_game_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": (
                    f"provider_game_id={body.provider_game_id!r} is not "
                    "an integer — primary metadata providers expose "
                    "integer ids."
                ),
                "errorCode": "invalid_provider_game_id",
            },
        ) from None

    platform = await db.execute(
        select(Platform).where(Platform.id == body.platform_id)
    )
    if platform.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"platform_id={body.platform_id} not found",
                "errorCode": "platform_not_found",
            },
        )

    # Slice 385 — validate the library_id when supplied; the
    # AddGame modal sends one but a scripted client may omit it.
    # When omitted (or when the modal raced the libraries query
    # and submitted before a value was set), fall back to the
    # first library by id so the auto-grab paths can resolve the
    # game's quality profile cascade instead of landing on the
    # global default (which the operator usually didn't tune).
    from romarr.libraries.models import Library

    resolved_library_id: int | None = body.library_id
    if resolved_library_id is not None:
        lib_exists = (
            await db.execute(
                select(Library.id).where(Library.id == resolved_library_id)
            )
        ).scalar_one_or_none()
        if lib_exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "errorMessage": f"library_id={body.library_id} not found",
                    "errorCode": "library_not_found",
                },
            )
    else:
        # Default to the first library — matches what the modal's
        # ``useEffect`` would have picked, but guarantees it even
        # for scripted callers / racy submits.
        fallback = (
            await db.execute(
                select(Library.id).order_by(Library.id.asc()).limit(1)
            )
        ).scalar_one_or_none()
        resolved_library_id = fallback

    base_slug = slugify_title(body.title)
    slug = await _allocate_unique_slug(
        db, platform_id=body.platform_id, base=base_slug
    )

    game = Game(
        platform_id=body.platform_id,
        slug=slug,
        title=body.title.strip(),
        monitored=body.monitored,
        library_id=resolved_library_id,
        # The aggregator runs on the next refresh cycle and pulls
        # everything else (summary, cover, release date, …) from
        # the configured provider priority list.
        needs_metadata_refresh=True,
    )
    setattr(game, column, provider_pk)

    db.add(game)
    await db.commit()
    await db.refresh(game)

    # Fire the aggregator inline so the GameRead we return carries
    # the enriched fields (cover, summary, release_date, genres…).
    # The operator just clicked Add — they expect the data on the
    # detail page they'll navigate to next, not on the next
    # scheduler tick. Bounded by a generous timeout so a stalled
    # provider can't hang the response forever; on timeout / error
    # the row stays in ``needs_metadata_refresh=True`` and the
    # scheduler picks it up later.
    import asyncio as _asyncio

    from romarr.metadata.refresh import refresh_game_metadata as _refresh

    try:
        await _asyncio.wait_for(
            _refresh(db, game_id=game.id, force=False),
            timeout=15.0,
        )
        await db.refresh(game)
    except Exception:
        # Best-effort. The aggregator's own logging surfaces the
        # actual error; a slow provider must not break the add.
        pass

    # Emit OnGameAdded so live operator sessions see the row land
    # immediately (spec 011 + spec 013 T068/T072 — fans out via the
    # WS bridge → ``gameAdded`` envelope). Best-effort: a missing
    # channel (test harness / disabled lifespan) is a silent no-op.
    if event_channel is not None:
        # Resolve the platform for the GameRef payload — already in
        # session cache from the existence check above.
        platform_row = await db.get(Platform, body.platform_id)
        if platform_row is not None:
            await event_channel.publish(
                OnGameAddedPayload(
                    game=GameRef(
                        id=game.id,
                        title=game.title,
                        platform_slug=platform_row.slug,
                        platform_name=platform_row.name,
                    ),
                )
            )

    return GameRead.model_validate(game, from_attributes=True)


# ---------------------------------------------------------------------------
# Integration endpoints — for external request managers (allseerr, …)
# ---------------------------------------------------------------------------
#
# A request manager (allseerr's *arr-style game service) only knows
# IGDB ids — it has no notion of Romarr's internal platform ids or
# libraries. These two endpoints give it an IGDB-native surface:
#   * POST /integrations/request — "acquire this IGDB game" (Radarr
#     role); Romarr resolves the platform via ``Platform.igdb_id``
#     and routes to the first library.
#   * GET  /integrations/status — "is this IGDB game already in the
#     Romarr library?" so the manager can show availability.


class IntegrationGameRequest(BaseModel):
    """POST body for ``/api/v3/game/integrations/request``.

    IGDB-native: the caller passes the IGDB game id + the IGDB
    *platform* id; Romarr maps the platform to its own catalogue via
    ``Platform.igdb_id`` and binds the game to the first library.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    igdb_id: Annotated[int, Field(alias="igdbId", ge=1)]
    igdb_platform_id: Annotated[int, Field(alias="igdbPlatformId", ge=1)]
    title: Annotated[str, Field(min_length=1, max_length=255)]
    monitored: bool = True


class IntegrationGameResult(BaseModel):
    """Response envelope for the integration request endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    # ``added`` — a new Game row was created.
    # ``already_present`` — the IGDB game already lives on this
    # platform; the existing row is returned untouched (idempotent).
    status: str
    game: GameRead


class IntegrationStatusResult(BaseModel):
    """Response for the integration status check."""

    model_config = ConfigDict(populate_by_name=True)

    present: bool
    games: list[GameRead]


@router.post(
    "/integrations/request",
    response_model=IntegrationGameResult,
    response_model_by_alias=False,
    summary=(
        "Acquire an IGDB game (external request managers). Resolves "
        "the IGDB platform to Romarr's catalogue and adds the game "
        "to the first library. Idempotent on (platform, igdb_id). "
        "Admin only."
    ),
)
async def integration_request_game(
    body: Annotated[IntegrationGameRequest, Body()],
    admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    event_channel: Annotated[EventChannel | None, Depends(get_event_channel)] = None,
) -> IntegrationGameResult:
    # 1. Map the IGDB platform id onto Romarr's own platform row.
    platform = (
        await db.execute(
            select(Platform).where(Platform.igdb_id == body.igdb_platform_id)
        )
    ).scalar_one_or_none()
    if platform is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": (
                    f"no Romarr platform maps to IGDB platform id "
                    f"{body.igdb_platform_id} — install the matching "
                    "Platform Pack first"
                ),
                "errorCode": "platform_not_supported",
            },
        )

    # 2. Idempotency — the IGDB game already on this platform?
    existing = (
        await db.execute(
            select(Game).where(
                Game.platform_id == platform.id,
                Game.igdb_id == body.igdb_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return IntegrationGameResult(
            status="already_present",
            game=GameRead.model_validate(existing, from_attributes=True),
        )

    # 3. Delegate to the standard add path — it handles slug
    #    allocation, the first-library fallback, the inline metadata
    #    refresh and the OnGameAdded event. ``providerName=igdb`` is
    #    a primary provider so the FK column is populated.
    game = await add_game_from_lookup(
        body=LookupAddRequest(
            providerName="igdb",
            providerGameId=str(body.igdb_id),
            title=body.title,
            platformId=platform.id,
            monitored=body.monitored,
        ),
        _admin=admin,
        db=db,
        event_channel=event_channel,
    )
    return IntegrationGameResult(status="added", game=game)


@router.get(
    "/integrations/status",
    response_model=IntegrationStatusResult,
    response_model_by_alias=False,
    summary=(
        "Check whether an IGDB game is already in the Romarr "
        "library (external request managers). Admin only."
    ),
)
async def integration_game_status(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    igdb_id: Annotated[int, Query(alias="igdbId", ge=1)],
) -> IntegrationStatusResult:
    rows = (
        await db.execute(select(Game).where(Game.igdb_id == igdb_id))
    ).scalars().all()
    return IntegrationStatusResult(
        present=len(rows) > 0,
        games=[GameRead.model_validate(r, from_attributes=True) for r in rows],
    )


class IntegrationPlatform(BaseModel):
    """One IGDB platform Romarr can acquire games for."""

    model_config = ConfigDict(populate_by_name=True)

    igdb_id: Annotated[int, Field(alias="igdbId")]
    name: str


class IntegrationPlatformsResult(BaseModel):
    """Response for the integration platforms listing."""

    model_config = ConfigDict(populate_by_name=True)

    platforms: list[IntegrationPlatform]


@router.get(
    "/integrations/platforms",
    response_model=IntegrationPlatformsResult,
    response_model_by_alias=False,
    summary=(
        "List the IGDB platforms Romarr can acquire games for "
        "(external request managers). A manager uses this to only "
        "offer a request button for platforms Romarr can resolve. "
        "Admin only."
    ),
)
async def integration_platforms(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationPlatformsResult:
    rows = (
        (
            await db.execute(
                select(Platform)
                .where(Platform.igdb_id.is_not(None))
                .order_by(Platform.name)
            )
        )
        .scalars()
        .all()
    )
    return IntegrationPlatformsResult(
        platforms=[
            IntegrationPlatform(igdb_id=p.igdb_id, name=p.name)
            for p in rows
            if p.igdb_id is not None
        ]
    )


__all__ = ["router"]
