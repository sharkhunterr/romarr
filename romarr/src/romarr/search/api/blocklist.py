"""Blocklist CRUD endpoints — /api/v3/blocklist*.

  - GET    /api/v3/blocklist        — list (admin)
  - POST   /api/v3/blocklist        — manual add (admin)
  - DELETE /api/v3/blocklist/{id}   — delete one entry (admin)

The append-only audit shape means there's no Update — modification
is a delete + re-create.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.search.blocklist import add_entry, delete_entry
from romarr.search.models import Blocklist
from romarr.search.schemas import BlocklistCreate, BlocklistRead

router = APIRouter(prefix="/api/v3/blocklist", tags=["Blocklist"])


@router.get(
    "",
    response_model=list[BlocklistRead],
    summary="List blocklist entries (admin only).",
)
async def list_blocklist(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BlocklistRead]:
    rows = (
        (await db.execute(select(Blocklist).order_by(Blocklist.added_at.desc())))
        .scalars()
        .all()
    )
    return [BlocklistRead.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "",
    response_model=BlocklistRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a blocklist entry (admin only).",
)
async def add_to_blocklist(
    body: Annotated[dict[str, object], Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BlocklistRead:
    try:
        payload = BlocklistCreate.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    row = await add_entry(
        db,
        indexer_id=payload.indexer_id,
        indexer_guid=payload.indexer_guid,
        release_title=payload.release_title,
        hash_sha1=payload.hash_sha1,
        hash_crc32=payload.hash_crc32,
        reason=payload.reason,
        added_by=payload.added_by,
    )
    return BlocklistRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a blocklist entry (admin only).",
)
async def remove_from_blocklist(
    entry_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    deleted = await delete_entry(db, entry_id=entry_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "blocklist_entry_not_found",
                "errorCode": "not_found",
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
