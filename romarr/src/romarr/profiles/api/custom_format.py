"""Custom Format CRUD — /api/v3/customformat.

The CRUD scaffold comes from :func:`make_crud_router`; the GET
endpoints are then replaced by CF-specific handlers that LEFT JOIN
``pack_sources`` to surface ``source_name`` (denormalized on the
read model so the UI can render "Communautaire · MonPack" without
a second call).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.platform_packs.models import PackSource
from romarr.profiles.api._shared import make_crud_router
from romarr.profiles.models import CustomFormat
from romarr.profiles.schemas import (
    CustomFormatCreate,
    CustomFormatRead,
    CustomFormatUpdate,
)

router = make_crud_router(
    label="customformat",
    base_path="/api/v3/customformat",
    tag="CustomFormats",
    model_cls=CustomFormat,
    schema_read=CustomFormatRead,
    schema_create=CustomFormatCreate,
    schema_update=CustomFormatUpdate,
)


def _row_to_read(row: CustomFormat, source_name: str | None) -> CustomFormatRead:
    """Build a ``CustomFormatRead`` and stamp the denormalized
    ``source_name`` for the frontend badge."""
    data = CustomFormatRead.model_validate(row, from_attributes=True)
    if source_name is not None:
        data = data.model_copy(update={"source_name": source_name})
    return data


# ---------------------------------------------------------------------------
# Overrides — replace the generic GET list + GET one with JOIN-enriched
# handlers. Order matters : APIRouter dispatches the FIRST match, so
# adding a route with the same path re-registers it (FastAPI keeps the
# first-registered handler). We work around this by clearing the
# matching entries before re-adding.
# ---------------------------------------------------------------------------


def _drop_route(path: str, method: str) -> None:
    """Remove a route from the shared CRUD router so the CF-specific
    handler below can register in its place."""
    keep = []
    for r in router.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set()):
            continue
        keep.append(r)
    router.routes[:] = keep


_drop_route("/api/v3/customformat", "GET")
_drop_route("/api/v3/customformat/{item_id}", "GET")


@router.get(
    "",
    response_model=list[CustomFormatRead],
    summary="List custom formats with source name enrichment (any authenticated user).",
)
async def list_custom_formats(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CustomFormatRead]:
    stmt = (
        select(CustomFormat, PackSource.name)
        .outerjoin(PackSource, CustomFormat.source_id == PackSource.id)
        .order_by(CustomFormat.score.desc(), CustomFormat.id.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [_row_to_read(cf, source_name) for cf, source_name in rows]


class _ToggleEnabledRequest(BaseModel):
    enabled: bool


@router.patch(
    "/{item_id}/enabled",
    response_model=CustomFormatRead,
    summary=(
        "Toggle a Custom Format on/off without flagging is_user_modified. "
        "A simple enable/disable is not a content edit — community sync "
        "keeps overwriting the seed body normally after the flip."
    ),
)
async def toggle_enabled(
    item_id: int,
    payload: _ToggleEnabledRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomFormatRead:
    row = (
        await db.execute(
            select(CustomFormat).where(CustomFormat.id == item_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "custom format not found",
                "errorCode": "customformat_not_found",
            },
        )
    row.enabled = payload.enabled
    await db.commit()
    await db.refresh(row)
    # Reload with source_name for a consistent response shape.
    join = (
        await db.execute(
            select(CustomFormat, PackSource.name)
            .outerjoin(PackSource, CustomFormat.source_id == PackSource.id)
            .where(CustomFormat.id == item_id)
        )
    ).one()
    cf, source_name = join
    return _row_to_read(cf, source_name)


@router.get(
    "/{item_id}",
    response_model=CustomFormatRead,
    summary="Read one custom format (any authenticated user).",
)
async def read_custom_format(
    item_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomFormatRead:
    row = (
        await db.execute(
            select(CustomFormat, PackSource.name)
            .outerjoin(PackSource, CustomFormat.source_id == PackSource.id)
            .where(CustomFormat.id == item_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"errorMessage": "custom format not found", "errorCode": "customformat_not_found"},
        )
    cf, source_name = row
    return _row_to_read(cf, source_name)
