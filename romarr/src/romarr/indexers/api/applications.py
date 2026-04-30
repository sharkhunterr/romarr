"""Prowlarr registration endpoints — /api/v3/applications/*.

  - GET    /api/v3/applications        — list registered Prowlarr instances
  - POST   /api/v3/applications        — register; returns plaintext app_token ONCE
  - GET    /api/v3/applications/{id}   — read one
  - DELETE /api/v3/applications/{id}   — unregister

All endpoints require the admin role from spec 010 (FR-013a, FR-026a).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.indexers.models import Application
from romarr.indexers.schemas import (
    ApplicationCreate,
    ApplicationCreateResult,
    ApplicationRead,
)
from romarr.indexers.tokens import generate_token, hash_token
from romarr.metadata.encryption import encrypt

router = APIRouter(prefix="/api/v3/applications", tags=["Indexers"])


def _to_read(row: Application) -> ApplicationRead:
    return ApplicationRead.model_validate(row)


@router.get(
    "",
    response_model=list[ApplicationRead],
    summary="List registered Prowlarr instances (admin only).",
)
async def list_applications(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApplicationRead]:
    rows = (
        (await db.execute(select(Application).order_by(Application.id)))
        .scalars()
        .all()
    )
    return [_to_read(r) for r in rows]


@router.get(
    "/{application_id}",
    response_model=ApplicationRead,
    summary="Read one Prowlarr application (admin only).",
)
async def read_application(
    application_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationRead:
    row = (
        await db.execute(
            select(Application).where(Application.id == application_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "application_not_found",
                "errorCode": "not_found",
            },
        )
    return _to_read(row)


@router.post(
    "",
    response_model=ApplicationCreateResult,
    status_code=status.HTTP_201_CREATED,
    summary="Register a Prowlarr instance (admin only). Returns app_token ONCE.",
)
async def register_application(
    payload: ApplicationCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationCreateResult:
    app_token = generate_token()
    encrypted_api_key = encrypt(json.dumps(payload.prowlarr_api_key).encode())

    row = Application(
        name=payload.name,
        sync_level=payload.sync_level,
        prowlarr_url=payload.prowlarr_url,
        prowlarr_api_key_encrypted=encrypted_api_key,
        app_token_hash=hash_token(app_token),
        enabled=True,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "duplicate_prowlarr_url",
                "errorCode": "duplicate",
                "details": "an application is already registered for this Prowlarr URL",
            },
        ) from exc
    await db.refresh(row)

    base = _to_read(row).model_dump()
    base["app_token"] = app_token
    return ApplicationCreateResult.model_validate(base)


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unregister a Prowlarr application (admin only). Token hash is dropped.",
)
async def unregister_application(
    application_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    row = (
        await db.execute(
            select(Application).where(Application.id == application_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "application_not_found",
                "errorCode": "not_found",
            },
        )
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
