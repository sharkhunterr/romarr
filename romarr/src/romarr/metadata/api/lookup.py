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


class GameLookupRow(BaseModel):
    """One row in the lookup response — a single provider candidate.

    Mirrors :class:`GameSearchResult` plus a deterministic ``rank``
    so the frontend can preserve the server-side ordering across
    React Query cache hits.
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
    truncated = merged[:limit]

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

    base_slug = slugify_title(body.title)
    slug = await _allocate_unique_slug(
        db, platform_id=body.platform_id, base=base_slug
    )

    game = Game(
        platform_id=body.platform_id,
        slug=slug,
        title=body.title.strip(),
        monitored=body.monitored,
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


__all__ = ["router"]
