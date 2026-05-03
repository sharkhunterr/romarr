"""Operator-facing metadata lookup endpoint.

  - GET /api/v3/game/lookup?q=...&platform_slug=...

Wraps :meth:`MetadataProvider.search_games` across every enabled
provider that has the search capability, collates the results, and
returns the union ranked by per-result confidence. The Frontend
AddNew page consumes this to surface candidates the operator can
add to the Library.

Network failures from any single provider are caught and dropped
from the response — partial results are better than no results
when the operator is mid-search.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.metadata.providers import MetadataProvider
from romarr.metadata.registry import load_enabled_providers
from romarr.metadata.types import GameSearchResult

router = APIRouter(prefix="/api/v3/game", tags=["Metadata"])


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
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
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

    return [
        GameLookupRow(
            rank=index,
            providerName=row.provider_name,
            providerGameId=row.provider_game_id,
            title=row.title,
            confidence=row.confidence,
        )
        for index, row in enumerate(truncated)
    ]


__all__ = ["router"]
