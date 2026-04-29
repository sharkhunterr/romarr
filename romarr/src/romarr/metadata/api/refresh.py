"""Admin endpoint to trigger metadata refresh for a single Game.

  - POST /api/v3/game/{game_id}/refresh-metadata?force=false

The endpoint is a thin wrapper around
:func:`romarr.metadata.refresh.refresh_game_metadata`. The full
:class:`AggregationResult` is returned so the operator (or the UI)
can show which provider won each field.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.metadata.refresh import refresh_game_metadata

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
