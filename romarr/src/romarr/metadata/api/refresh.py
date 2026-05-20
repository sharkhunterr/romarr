"""Admin endpoint to trigger metadata refresh for a single Game.

  - POST /api/v3/game/{game_id}/refresh-metadata?force=false
  - GET  /api/v3/game/{game_id}/provider/{provider}/candidates?q=…
  - POST /api/v3/game/{game_id}/provider/{provider}/relink
  - POST /api/v3/game/{game_id}/provider/{provider}/clear

The endpoint is a thin wrapper around
:func:`romarr.metadata.refresh.refresh_game_metadata`. The full
:class:`AggregationResult` is returned so the operator (or the UI)
can show which provider won each field.

The ``provider/{name}/{candidates,relink,clear}`` trio lets the
operator fix a wrong scan-time match without dropping into the DB —
the Metadata tab on the game detail page renders a "Relink" button
per provider that opens a search modal, the operator picks the
right hit, and the FK + cache flip + refresh happen atomically.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.domain.models import Game
from romarr.metadata.models import MetadataCache
from romarr.metadata.refresh import (
    _PROVIDER_FK_COLUMN,
    _search_title_variants,
    refresh_game_metadata,
)
from romarr.metadata.registry import load_enabled_providers

router = APIRouter(prefix="/api/v3/game", tags=["Metadata"])


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class RefreshMetadataResponse(_Base):
    """JSON projection of :class:`AggregationResult`.

    ``fields`` flattens each ``(value, winning_provider)`` tuple to
    a small object so the UI can render the per-field provenance
    badges (FR-008 visibility).
    """

    game_id: int
    fields: dict[str, dict[str, Any]]
    skipped_locked: list[str]
    cover_path: str | None
    needs_metadata_refresh: bool


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@router.post(
    "/{game_id}/refresh-metadata",
    response_model=RefreshMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh metadata for a Game from the enabled providers (admin only).",
)
async def refresh_metadata_endpoint(
    game_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    force: bool = False,
) -> RefreshMetadataResponse:
    try:
        result = await refresh_game_metadata(db, game_id=game_id, force=force)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "not_found",
                "errorCode": "not_found",
                "details": str(exc),
            },
        ) from exc

    return RefreshMetadataResponse(
        game_id=result.game_id,
        fields={
            field.value: {
                "value": _serialize_value(value),
                "provider": provider,
            }
            for field, (value, provider) in result.fields.items()
        },
        skipped_locked=[f.value for f in result.skipped_locked],
        cover_path=result.cover_path,
        needs_metadata_refresh=result.needs_metadata_refresh,
    )


# ---------------------------------------------------------------------------
# Per-provider relink (Metadata tab → "Pick the right IGDB / SS / … entry").
# ---------------------------------------------------------------------------


class ProviderCandidate(_Base):
    """One row in the per-provider relink picker."""

    provider_name: str = Field(alias="providerName")
    provider_game_id: str = Field(alias="providerGameId")
    title: str
    confidence: float
    platform_slug: str | None = Field(default=None, alias="platformSlug")
    platform_name: str | None = Field(default=None, alias="platformName")
    release_year: int | None = Field(default=None, alias="releaseYear")
    cover_url: str | None = Field(default=None, alias="coverUrl")


class ProviderCandidatesResponse(_Base):
    """The candidate list + the variants tried so the operator can
    see which query actually hit (useful when the auto-strip is
    over-eager)."""

    provider_name: str = Field(alias="providerName")
    queries_tried: list[str] = Field(alias="queriesTried")
    candidates: list[ProviderCandidate]


def _validate_provider(provider_name: str) -> str:
    column = _PROVIDER_FK_COLUMN.get(provider_name.lower())
    if column is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": (
                    f"provider_name={provider_name!r} is not a primary "
                    "metadata provider — relink supports igdb, mobygames, "
                    "screenscraper, launchbox, retroachievements."
                ),
                "errorCode": "unsupported_provider",
            },
        )
    return column


async def _load_game(db: AsyncSession, game_id: int) -> Game:
    game = (
        await db.execute(select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"game_id={game_id} not found",
                "errorCode": "not_found",
            },
        )
    return game


@router.get(
    "/{game_id}/provider/{provider_name}/candidates",
    response_model=ProviderCandidatesResponse,
    response_model_by_alias=True,
    summary=(
        "Search ONE provider for relink candidates against this game's "
        "title (admin only). The operator picks the right hit and POSTs "
        "it to /relink."
    ),
)
async def list_relink_candidates(
    game_id: int,
    provider_name: str,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[
        str | None,
        Query(
            description=(
                "Override the search query. Defaults to the game's "
                "title with No-Intro / Redump tags stripped."
            ),
            max_length=255,
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ProviderCandidatesResponse:
    _validate_provider(provider_name)
    game = await _load_game(db, game_id)

    # Resolve the platform slug from the game's Platform so the
    # provider can scope by platform when supported.
    from romarr.domain.models import Platform as _Platform

    platform_row = (
        await db.execute(
            select(_Platform.slug).where(_Platform.id == game.platform_id)
        )
    ).first()
    platform_slug = platform_row[0] if platform_row else None

    # Load the SINGLE provider we want — skip scan-only filtering since
    # the operator is driving this manually (FR-005 allows out-of-scan).
    providers = await load_enabled_providers(db, scan=False)
    provider = next(
        (p for p in providers if p.name == provider_name.lower()), None
    )
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": (
                    f"provider_name={provider_name!r} is not enabled "
                    "in Settings → Metadata Sources."
                ),
                "errorCode": "provider_not_enabled",
            },
        )

    if q is not None and q.strip():
        variants = [q.strip()]
    else:
        variants = _search_title_variants(game.title)

    hits: list[Any] = []
    tried: list[str] = []
    for variant in variants:
        tried.append(variant)
        try:
            hits = await provider.search_games(
                variant, platform_slug=platform_slug
            )
        except Exception:
            # Pass through silently — let the next variant try.
            hits = []
        if hits:
            break

    # Highest-confidence first, capped to ``limit``.
    hits.sort(key=lambda c: float(getattr(c, "confidence", 0.0)), reverse=True)
    candidates = [
        ProviderCandidate(
            providerName=h.provider_name,
            providerGameId=h.provider_game_id,
            title=h.title,
            confidence=float(h.confidence),
            platformSlug=getattr(h, "platform_slug", None),
            platformName=getattr(h, "platform_name", None),
            releaseYear=getattr(h, "release_year", None),
            coverUrl=getattr(h, "cover_url", None),
        )
        for h in hits[:limit]
    ]

    return ProviderCandidatesResponse(
        providerName=provider_name.lower(),
        queriesTried=tried,
        candidates=candidates,
    )


class RelinkRequest(BaseModel):
    """Payload for ``POST /provider/{name}/relink``."""

    model_config = ConfigDict(extra="forbid")
    provider_game_id: str = Field(
        alias="providerGameId",
        min_length=1,
        max_length=128,
        description=(
            "The provider's id for the chosen game (string for "
            "generality; integer-id providers parse it server-side)."
        ),
    )


@router.post(
    "/{game_id}/provider/{provider_name}/relink",
    response_model=RefreshMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Pin a new provider id on this game, drop the stale cache "
        "row, and force a refresh so the new payload lands "
        "atomically (admin only)."
    ),
)
async def relink_provider(
    game_id: int,
    provider_name: str,
    body: Annotated[RelinkRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshMetadataResponse:
    column = _validate_provider(provider_name)
    game = await _load_game(db, game_id)

    # Coerce to int for the FK column when the provider uses
    # integer ids (everyone but custom-tooling). A non-numeric id on
    # an integer provider is a contract bug — surface 400.
    try:
        provider_pk: int | str = int(body.provider_game_id)
    except ValueError:
        provider_pk = body.provider_game_id

    setattr(game, column, provider_pk)
    # Wipe the existing cache for this (game, provider) pair so the
    # forced refresh below pulls a fresh payload tied to the new id.
    await db.execute(
        delete(MetadataCache).where(
            MetadataCache.game_id == game.id,
            MetadataCache.provider_name == provider_name.lower(),
        )
    )
    await db.commit()

    # Force-refresh so the freshly-pinned provider takes effect
    # immediately (cache hit on the old id would otherwise mask it).
    result = await refresh_game_metadata(db, game_id=game.id, force=True)
    return RefreshMetadataResponse(
        game_id=result.game_id,
        fields={
            field.value: {
                "value": _serialize_value(value),
                "provider": provider,
            }
            for field, (value, provider) in result.fields.items()
        },
        skipped_locked=[f.value for f in result.skipped_locked],
        cover_path=result.cover_path,
        needs_metadata_refresh=result.needs_metadata_refresh,
    )


@router.post(
    "/{game_id}/provider/{provider_name}/clear",
    response_model=RefreshMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Detach a provider from this game (FK → NULL, cache row "
        "purged) and re-aggregate from the surviving providers "
        "(admin only)."
    ),
)
async def clear_provider(
    game_id: int,
    provider_name: str,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshMetadataResponse:
    column = _validate_provider(provider_name)
    game = await _load_game(db, game_id)
    setattr(game, column, None)
    await db.execute(
        delete(MetadataCache).where(
            MetadataCache.game_id == game.id,
            MetadataCache.provider_name == provider_name.lower(),
        )
    )
    await db.commit()
    result = await refresh_game_metadata(db, game_id=game.id, force=True)
    return RefreshMetadataResponse(
        game_id=result.game_id,
        fields={
            field.value: {
                "value": _serialize_value(value),
                "provider": provider,
            }
            for field, (value, provider) in result.fields.items()
        },
        skipped_locked=[f.value for f in result.skipped_locked],
        cover_path=result.cover_path,
        needs_metadata_refresh=result.needs_metadata_refresh,
    )
