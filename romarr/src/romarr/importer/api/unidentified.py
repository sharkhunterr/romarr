"""Unidentified-dump endpoints — `/api/v3/rom/unidentified*`.

  * GET    /api/v3/rom/unidentified         — list (any authenticated user)
  * DELETE /api/v3/rom/unidentified/{id}    — admin; **does NOT delete
                                              the source file** (FR-038)

The match endpoint (POST /api/v3/rom/unidentified/{id}/match) is
the operator's "I know what this is, please import it" surface;
it depends on the orchestrator's run_import end-to-end and lands
with the HARD slice.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.domain.models import UnidentifiedDump
from romarr.importer.schemas import UnidentifiedDumpRead

router = APIRouter(prefix="/api/v3/rom/unidentified", tags=["Importer"])


@router.get(
    "",
    response_model=list[UnidentifiedDumpRead],
    summary="List unidentified dumps (any authenticated user).",
)
async def list_unidentified(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    library_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UnidentifiedDumpRead]:
    stmt = select(UnidentifiedDump).order_by(
        UnidentifiedDump.discovered_at.desc()
    )
    if library_id is not None:
        stmt = stmt.where(UnidentifiedDump.library_id == library_id)
    stmt = stmt.limit(limit).offset(offset)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        UnidentifiedDumpRead.model_validate(r, from_attributes=True)
        for r in rows
    ]


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Delete an unidentified-dump row (admin only). The source "
        "file on disk is NOT removed (FR-038)."
    ),
)
async def delete_unidentified(
    entry_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    row = (
        await db.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.id == entry_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "unidentified_dump_not_found",
                "errorCode": "not_found",
            },
        )
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
