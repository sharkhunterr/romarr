"""Platform override + format-CRUD endpoints — /api/v3/rom/platform/*.

  - GET     /api/v3/rom/platform                       — list platforms
  - POST    /api/v3/rom/platform/{id}/override         — mark overridden
  - DELETE  /api/v3/rom/platform/{id}/override         — release override
  - GET     /api/v3/rom/platform/{id}/format           — list formats
  - POST    /api/v3/rom/platform/{id}/format           — add format
  - PUT     /api/v3/rom/platform/{id}/format/{fmt_id}  — update format
  - DELETE  /api/v3/rom/platform/{id}/format/{fmt_id}  — delete format

The bare ``GET`` is readonly: any authenticated user can pull the
platform catalogue (it drives Library / Wanted / AddNew filters
on the frontend). Mutating endpoints all require the ``admin``
role (FR-026a). Format mutation also requires the platform's
``pack_source = 'user'`` (FR-026) — enforced inside the override
module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.domain.models import Platform, PlatformFormat
from romarr.domain.schemas import PlatformRead
from romarr.platform_packs import (
    OverrideRequiredError,
    add_format,
    delete_format,
    mark_overridden,
    release_override,
    update_format,
)

router = APIRouter(prefix="/api/v3/rom/platform", tags=["Platform Packs"])


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class PlatformOverrideResponse(_Base):
    id: int
    slug: str
    pack_source: str
    pack_version: str | None


class FormatRead(_Base):
    id: int
    extension: str
    format_type: str
    min_size_bytes: int | None
    max_size_bytes: int | None
    pack_source: str


class FormatCreate(_Base):
    extension: Annotated[str, Field(pattern=r"^\.[A-Za-z0-9]+$")]
    format_type: Annotated[
        str,
        Field(pattern=r"^(?:cartridge|disc|compressed|archive|package)$"),
    ]
    min_size_bytes: int | None = Field(default=None, ge=0)
    max_size_bytes: int | None = Field(default=None, ge=0)


class FormatUpdate(_Base):
    extension: Annotated[
        str | None, Field(default=None, pattern=r"^\.[A-Za-z0-9]+$")
    ] = None
    format_type: Annotated[
        str | None,
        Field(
            default=None,
            pattern=r"^(?:cartridge|disc|compressed|archive|package)$",
        ),
    ] = None
    min_size_bytes: int | None = Field(default=None, ge=0)
    max_size_bytes: int | None = Field(default=None, ge=0)


def _override_to_409(exc: OverrideRequiredError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "errorMessage": "override_required",
            "errorCode": "override_required",
            "details": str(exc),
        },
    )


def _platform_to_override_response(p: Platform) -> PlatformOverrideResponse:
    return PlatformOverrideResponse(
        id=p.id,
        slug=p.slug,
        pack_source=p.pack_source,
        pack_version=p.pack_version,
    )


def _format_to_read(f: PlatformFormat) -> FormatRead:
    return FormatRead(
        id=f.id,
        extension=f.extension,
        format_type=f.format_type,
        min_size_bytes=f.min_size_bytes,
        max_size_bytes=f.max_size_bytes,
        pack_source=f.pack_source,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[PlatformRead],
    summary=(
        "List every platform in the catalogue (any authenticated "
        "user). Drives the Library / Wanted / AddNew filter "
        "dropdowns on the frontend."
    ),
)
async def list_platforms(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PlatformRead]:
    rows = (
        await db.execute(select(Platform).order_by(Platform.name.asc()))
    ).scalars().all()
    return [
        PlatformRead.model_validate(row, from_attributes=True) for row in rows
    ]


# ---------------------------------------------------------------------------
# Override
# ---------------------------------------------------------------------------


@router.post(
    "/{platform_id}/override",
    response_model=PlatformOverrideResponse,
    summary="Mark a platform as user-overridden (admin only). Idempotent.",
)
async def post_override(
    platform_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformOverrideResponse:
    try:
        platform = await mark_overridden(db, platform_id=platform_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "platform_not_found",
                "errorCode": "not_found",
                "details": str(exc),
            },
        ) from exc
    return _platform_to_override_response(platform)


@router.delete(
    "/{platform_id}/override",
    response_model=PlatformOverrideResponse,
    summary="Release a user-override (admin only).",
)
async def delete_override(
    platform_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformOverrideResponse:
    try:
        platform = await release_override(db, platform_id=platform_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "platform_not_found",
                "errorCode": "not_found",
                "details": str(exc),
            },
        ) from exc
    return _platform_to_override_response(platform)


# ---------------------------------------------------------------------------
# Format CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/{platform_id}/format",
    response_model=list[FormatRead],
    summary="List a platform's formats (admin only).",
)
async def list_formats(
    platform_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FormatRead]:
    rows = (
        (
            await db.execute(
                select(PlatformFormat).where(
                    PlatformFormat.platform_id == platform_id
                )
            )
        )
        .scalars()
        .all()
    )
    return [_format_to_read(r) for r in rows]


@router.post(
    "/{platform_id}/format",
    response_model=FormatRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a format (admin only). Platform must be user-overridden.",
)
async def post_format(
    platform_id: int,
    payload: FormatCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FormatRead:
    try:
        row = await add_format(
            db,
            platform_id=platform_id,
            extension=payload.extension,
            format_type=payload.format_type,
            min_size_bytes=payload.min_size_bytes,
            max_size_bytes=payload.max_size_bytes,
        )
    except OverrideRequiredError as exc:
        raise _override_to_409(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "platform_not_found",
                "errorCode": "not_found",
                "details": str(exc),
            },
        ) from exc
    return _format_to_read(row)


@router.put(
    "/{platform_id}/format/{format_id}",
    response_model=FormatRead,
    summary="Update a format (admin only). Platform must be user-overridden.",
)
async def put_format(
    platform_id: int,
    format_id: int,
    payload: FormatUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FormatRead:
    fields = payload.model_dump(exclude_unset=True)
    try:
        row = await update_format(db, format_id=format_id, **fields)
    except OverrideRequiredError as exc:
        raise _override_to_409(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "format_not_found",
                "errorCode": "not_found",
                "details": str(exc),
            },
        ) from exc
    if row.platform_id != platform_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "format_not_on_platform",
                "errorCode": "not_found",
            },
        )
    return _format_to_read(row)


@router.delete(
    "/{platform_id}/format/{format_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a format (admin only). Idempotent.",
)
async def delete_format_endpoint(
    platform_id: int,
    format_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        deleted = await delete_format(db, format_id=format_id)
    except OverrideRequiredError as exc:
        raise _override_to_409(exc) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "format_not_found",
                "errorCode": "not_found",
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
