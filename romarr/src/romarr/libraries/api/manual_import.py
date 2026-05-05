"""Manual-import HTTP surface (spec 009 T079, T083).

Two routes:

  * GET ``/api/v3/rom/manual-import?folder=<path>`` —
    pre-flight listing (FR-022 — read-only). Returns the
    candidate grid with parser hints + Game suggestions.
  * POST ``/api/v3/rom/manual-import`` — bulk operator decisions.
    Accepts a list of per-entry actions; delegates to
    :func:`romarr.libraries.manual_import.bulk_import` which
    fans out to the orchestrator.

GET is admin-gated per CL007 (FR-033a — folder= surface
exposes a path-traversal vector that requires the same
guarantee as the mutating endpoints). POST is admin-gated as a
mutating action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.libraries.manual_import import (
    ManualImportRequest,
    bulk_import,
    list_candidates,
)

router = APIRouter(prefix="/api/v3/rom/manual-import", tags=["Library"])


_DEFAULT_ACCEPTED_EXTENSIONS = {
    ".md", ".gen", ".bin", ".smc", ".sfc", ".nes", ".gb", ".gbc",
    ".gba", ".n64", ".z64", ".v64", ".iso", ".cue", ".chd",
    ".7z", ".zip", ".rar",
}


class ManualImportListingRead(BaseModel):
    """Wire shape for one candidate row."""

    path: str
    size_bytes: int
    parsed_title: str | None = None
    parsed_convention: str | None = None
    parsed_regions: list[str] = Field(default_factory=list)
    parsed_languages: list[str] = Field(default_factory=list)
    suggested_platform_id: int | None = None
    suggested_game_id: int | None = None


class ManualImportRequestPayload(BaseModel):
    """One row in the bulk-import POST body."""

    path: str
    library_id: int | None = None
    action: Literal["import", "skip"] = "import"
    game_id_override: int | None = None


class BulkImportPayload(BaseModel):
    """Bulk-import POST request body."""

    entries: list[ManualImportRequestPayload]


class ManualImportResultRead(BaseModel):
    """Per-entry outcome on the bulk-import response."""

    path: str
    action: Literal["import", "skip"]
    success: bool
    history_id: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    correlation_id: UUID | None = None


@router.get("", response_model=list[ManualImportListingRead])
async def get_manual_import_listing(
    request: Request,
    _admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    folder: str = Query(..., description="Absolute path to walk."),
) -> list[ManualImportListingRead]:
    """Walk ``folder`` and return the manual-import candidate grid.

    Read-only — no DB writes (FR-022).
    """
    folder_path = Path(folder)
    if not folder_path.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "folder must be an absolute path",
                "errorCode": "invalid_folder",
            },
        )

    listings = await list_candidates(
        session=session,
        folder=folder_path,
        accepted_extensions=_DEFAULT_ACCEPTED_EXTENSIONS,
    )
    return [
        ManualImportListingRead(
            path=str(listing.path),
            size_bytes=listing.size_bytes,
            parsed_title=listing.parsed_title,
            parsed_convention=listing.parsed_convention,
            parsed_regions=list(listing.parsed_regions),
            parsed_languages=list(listing.parsed_languages),
            suggested_platform_id=listing.suggested_platform_id,
            suggested_game_id=listing.suggested_game_id,
        )
        for listing in listings
    ]


@router.post(
    "",
    response_model=list[ManualImportResultRead],
    status_code=status.HTTP_200_OK,
)
async def post_manual_import_bulk(
    payload: BulkImportPayload,
    request: Request,
    admin: Annotated[Principal, Depends(require_admin)],
) -> list[ManualImportResultRead]:
    """Run the operator's bulk decisions against the importer."""
    sm = request.app.state.db_sessionmaker
    requests = [
        ManualImportRequest(
            path=Path(entry.path),
            library_id=entry.library_id,
            action=entry.action,
            game_id_override=entry.game_id_override,
        )
        for entry in payload.entries
    ]
    results = await bulk_import(
        sessionmaker=sm,
        entries=requests,
        imported_by=getattr(admin, "username", "manual"),
    )
    return [
        ManualImportResultRead(
            path=str(result.path),
            action=result.action,
            success=result.success,
            history_id=result.history_id,
            error_code=result.error_code,
            error_message=result.error_message,
            correlation_id=result.correlation_id,
        )
        for result in results
    ]


__all__ = ["router"]
