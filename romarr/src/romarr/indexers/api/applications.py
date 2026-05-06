"""Prowlarr registration endpoints — /api/v3/applications/*.

  - GET    /api/v3/applications        — list registered Prowlarr instances
  - POST   /api/v3/applications        — register; returns plaintext app_token ONCE
  - GET    /api/v3/applications/{id}   — read one
  - DELETE /api/v3/applications/{id}   — unregister

All endpoints require the admin role from spec 010 (FR-013a, FR-026a).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.auth.api_keys import create_api_key
from romarr.auth.constants import SCOPE_ADMIN
from romarr.auth.models import ApiKey, User
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
    admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationCreateResult:
    from romarr.indexers.api.indexers import _clean_secret, _normalize_indexer_url

    cleaned_key = _clean_secret(payload.prowlarr_api_key) or ""
    encrypted_api_key = encrypt(cleaned_key.encode("utf-8"))
    normalized_prowlarr_url = _normalize_indexer_url(payload.prowlarr_url)

    # Mint a real Romarr API key (admin scope) so Prowlarr can
    # authenticate to Romarr's REST surface via the standard
    # ``X-Api-Key`` header — that's what Prowlarr's Sonarr-app
    # client expects in its "API Key" field. The custom
    # ``app_token`` design didn't survive contact with Prowlarr's
    # Sonarr-compat client; we keep the field name on the wire
    # for backward compat, but the value IS now a Romarr API
    # key plaintext.
    admin_user = await db.get(User, admin.user_id)
    if admin_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "errorMessage": "user_not_found",
                "errorCode": "forbidden",
            },
        )
    minted = await create_api_key(
        db,
        user=admin_user,
        name=f"Prowlarr — {payload.name}",
        scopes=[SCOPE_ADMIN],
    )

    row = Application(
        name=payload.name,
        sync_level=payload.sync_level,
        prowlarr_url=normalized_prowlarr_url,
        prowlarr_api_key_encrypted=encrypted_api_key,
        # Track the api_key row in the existing token-hash column
        # so rotate / unregister can revoke the right key without
        # a new schema migration. Format: ``apikey:{id}``.
        app_token_hash=f"apikey:{minted.api_key_id}",
        enabled=True,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Roll back the minted API key too so we don't leave
        # an orphan row when the application insert collides.
        await db.rollback()
        await _revoke_api_key(db, minted.api_key_id)
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
    base["app_token"] = minted.plaintext
    return ApplicationCreateResult.model_validate(base)


async def _revoke_api_key(db: AsyncSession, api_key_id: int) -> None:
    """Best-effort delete of a previously-minted application API key."""
    row = (
        await db.execute(select(ApiKey).where(ApiKey.id == api_key_id))
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()


def _api_key_id_from_token_hash(token_hash: str) -> int | None:
    """Extract the api_key_id encoded in ``app_token_hash``.

    New rows store ``apikey:{id}``; legacy rows (pre-rework) have a
    BLAKE2b hex hash with no prefix. The latter return ``None`` so
    we fall through to the legacy revoke path (drop the row only).
    """
    if not token_hash.startswith("apikey:"):
        return None
    try:
        return int(token_hash.removeprefix("apikey:"))
    except ValueError:
        return None


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
    # Revoke the API key the registration minted so Prowlarr loses
    # access at the same time the row goes.
    key_id = _api_key_id_from_token_hash(row.app_token_hash)
    if key_id is not None:
        key_row = (
            await db.execute(select(ApiKey).where(ApiKey.id == key_id))
        ).scalar_one_or_none()
        if key_row is not None:
            await db.delete(key_row)
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{application_id}/rotate-token",
    response_model=ApplicationCreateResult,
    summary=(
        "Mint a fresh API key for an existing application (admin only). "
        "The previous key stops authenticating immediately. "
        "Returns the new plaintext key EXACTLY ONCE."
    ),
)
async def rotate_application_token(
    application_id: int,
    admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationCreateResult:
    """Operator lost the original API key (we only kept the hash);
    rotate to mint a fresh one. The Prowlarr URL + Prowlarr-side
    API key stay unchanged — only the Romarr key Prowlarr uses to
    call back changes."""
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

    # Revoke the prior API key.
    old_key_id = _api_key_id_from_token_hash(row.app_token_hash)
    if old_key_id is not None:
        old_key = (
            await db.execute(select(ApiKey).where(ApiKey.id == old_key_id))
        ).scalar_one_or_none()
        if old_key is not None:
            await db.delete(old_key)

    # Mint a fresh one.
    admin_user = await db.get(User, admin.user_id)
    if admin_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "errorMessage": "user_not_found",
                "errorCode": "forbidden",
            },
        )
    minted = await create_api_key(
        db,
        user=admin_user,
        name=f"Prowlarr — {row.name}",
        scopes=[SCOPE_ADMIN],
    )
    row.app_token_hash = f"apikey:{minted.api_key_id}"
    await db.commit()
    await db.refresh(row)

    base = _to_read(row).model_dump()
    base["app_token"] = minted.plaintext
    return ApplicationCreateResult.model_validate(base)
