"""Library CRUD endpoints — /api/v3/rom/library*.

  * POST   /api/v3/rom/library        — create (admin)
  * GET    /api/v3/rom/library        — list (any authenticated user)
  * GET    /api/v3/rom/library/{id}   — read (any authenticated user)
  * PUT    /api/v3/rom/library/{id}   — partial update (admin)
  * DELETE /api/v3/rom/library/{id}   — delete with optional ?force=true (admin)

Per FR-032a, reads are open to ``require_readonly`` and mutations
require ``require_admin``. The path-existence + writability check
in FR-004 is enforced by the handler (not by Pydantic), since the
schema layer must stay filesystem-free.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.domain.models import Dump, Release
from romarr.libraries.models import Library, LibraryPlatform
from romarr.libraries.schemas import (
    LibraryCreate,
    LibraryRead,
    LibraryUpdate,
)
from romarr.metadata.encryption import encrypt

router = APIRouter(prefix="/api/v3/rom/library", tags=["Libraries"])


# ---------------------------------------------------------------------------
# Helpers


def _path_unwritable_error(path: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "errorMessage": "library_path_unwritable",
            "errorCode": "path_unwritable",
            "details": (
                f"library.path {path!r} must exist and be writable at save time"
            ),
        },
    )


def _validate_path_writable(raw_path: str) -> None:
    """Raise HTTP 400 if ``raw_path`` does not exist or is not writable."""
    path = Path(raw_path)
    if not path.exists() or not path.is_dir():
        raise _path_unwritable_error(raw_path)
    if not os.access(path, os.W_OK):
        raise _path_unwritable_error(raw_path)


def _not_found(library_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "errorMessage": "library_not_found",
            "errorCode": "not_found",
            "details": f"no library with id={library_id}",
        },
    )


def _conflict(*, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "errorMessage": message,
            "errorCode": code,
        },
    )


def _duplicate_name() -> HTTPException:
    return _conflict(
        code="duplicate",
        message="a library with the same name already exists",
    )


async def _platform_ids_for(db: AsyncSession, library_id: int) -> list[int]:
    rows = await db.execute(
        select(LibraryPlatform.platform_id).where(
            LibraryPlatform.library_id == library_id
        )
    )
    return sorted(rows.scalars().all())


async def _read_payload(db: AsyncSession, row: Library) -> LibraryRead:
    platform_ids = await _platform_ids_for(db, row.id)
    return LibraryRead.from_orm_with_platforms(row, platform_ids)


def _maybe_encrypt(plaintext: str | None) -> bytes | None:
    if plaintext is None:
        return None
    return encrypt(plaintext.encode("utf-8"))


# ---------------------------------------------------------------------------
# Endpoints


@router.post(
    "",
    response_model=LibraryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a library (admin only).",
)
async def create_library(
    body: Annotated[dict[str, Any], Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryRead:
    try:
        payload = LibraryCreate.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    _validate_path_writable(payload.path)

    api_key_plain = (
        payload.exporter_romm_api_key.get_secret_value()
        if payload.exporter_romm_api_key is not None
        else None
    )

    row = Library(
        name=payload.name,
        path=payload.path,
        platform_subfolders=payload.platform_subfolders,
        platforms_restricted=payload.platforms_restricted,
        quality_profile_id=payload.quality_profile_id,
        region_profile_id=payload.region_profile_id,
        dump_profile_id=payload.dump_profile_id,
        language_profile_id=payload.language_profile_id,
        naming_profile_id=payload.naming_profile_id,
        monitored_default=payload.monitored_default,
        use_hardlinks=payload.use_hardlinks,
        lifecycle_policy=payload.lifecycle_policy,
        delete_after_import=payload.delete_after_import,
        keep_dump_history=payload.keep_dump_history,
        min_disk_free_gb=payload.min_disk_free_gb,
        preserve_archive=payload.preserve_archive,
        exporter_romm_enabled=payload.exporter_romm_enabled,
        exporter_romm_url=payload.exporter_romm_url,
        exporter_romm_api_key_encrypted=_maybe_encrypt(api_key_plain),
        exporter_esde_enabled=payload.exporter_esde_enabled,
        exporter_pegasus_enabled=payload.exporter_pegasus_enabled,
        exporter_launchbox_enabled=payload.exporter_launchbox_enabled,
        exporter_launchbox_per_platform=payload.exporter_launchbox_per_platform,
        scan_poll_seconds=payload.scan_poll_seconds,
        heartbeat_seconds=payload.heartbeat_seconds,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _duplicate_name() from exc

    for platform_id in payload.platform_ids:
        db.add(LibraryPlatform(library_id=row.id, platform_id=platform_id))
    await db.commit()
    await db.refresh(row)

    return await _read_payload(db, row)


@router.get(
    "",
    response_model=list[LibraryRead],
    summary="List all libraries (any authenticated user).",
)
async def list_libraries(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LibraryRead]:
    rows = (
        (await db.execute(select(Library).order_by(Library.id))).scalars().all()
    )
    return [await _read_payload(db, row) for row in rows]


@router.get(
    "/{library_id}",
    response_model=LibraryRead,
    summary="Read a single library (any authenticated user).",
)
async def read_library(
    library_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryRead:
    row = (
        await db.execute(select(Library).where(Library.id == library_id))
    ).scalar_one_or_none()
    if row is None:
        raise _not_found(library_id)
    return await _read_payload(db, row)


@router.put(
    "/{library_id}",
    response_model=LibraryRead,
    summary="Partial update of a library (admin only).",
)
async def update_library(
    library_id: int,
    body: Annotated[dict[str, Any], Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryRead:
    row = (
        await db.execute(select(Library).where(Library.id == library_id))
    ).scalar_one_or_none()
    if row is None:
        raise _not_found(library_id)

    try:
        payload = LibraryUpdate.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    if payload.path is not None and payload.path != row.path:
        _validate_path_writable(payload.path)

    diff = payload.model_dump(exclude_unset=True, exclude={"platform_ids", "exporter_romm_api_key"})
    for field, value in diff.items():
        setattr(row, field, value)

    if payload.exporter_romm_api_key is not None:
        row.exporter_romm_api_key_encrypted = _maybe_encrypt(
            payload.exporter_romm_api_key.get_secret_value()
        )

    if payload.platform_ids is not None:
        await db.execute(
            delete(LibraryPlatform).where(
                LibraryPlatform.library_id == library_id
            )
        )
        for platform_id in payload.platform_ids:
            db.add(LibraryPlatform(library_id=library_id, platform_id=platform_id))

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _duplicate_name() from exc

    await db.refresh(row)
    return await _read_payload(db, row)


@router.delete(
    "/{library_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Delete a library (admin only). ``?force=true`` unbinds attached "
        "Releases first; rejected when ``keep_dump_history=true`` and "
        "historical Dumps reference the library (FR-027)."
    ),
)
async def delete_library(
    library_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    force: Annotated[
        bool,
        Query(description="Unbind attached Releases before deleting"),
    ] = False,
) -> Response:
    row = (
        await db.execute(select(Library).where(Library.id == library_id))
    ).scalar_one_or_none()
    if row is None:
        raise _not_found(library_id)

    attached_count = (
        await db.execute(
            select(Release.id)
            .where(Release.library_id == library_id)
            .limit(1)
        )
    ).first()

    if row.keep_dump_history:
        historical_dump = (
            await db.execute(
                select(Dump.id)
                .join(Release, Release.id == Dump.release_id)
                .where(Release.library_id == library_id)
                .limit(1)
            )
        ).first()
        if historical_dump is not None:
            raise _conflict(
                code="historical_dumps_present",
                message=(
                    "library has historical Dumps and keep_dump_history is "
                    "enabled; delete or move the dumps before deleting "
                    "the library"
                ),
            )

    if attached_count is not None and not force:
        raise _conflict(
            code="library_in_use",
            message=(
                "library has attached Releases; pass ?force=true to unbind "
                "them (files on disk are not touched)"
            ),
        )

    if force:
        await db.execute(
            update(Release)
            .where(Release.library_id == library_id)
            .values(library_id=None)
        )

    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
