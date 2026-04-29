"""Admin user-CRUD endpoints — /api/v3/user/*.

Per spec 010 FR-026 every endpoint here requires the ``admin`` role.
Per User Story 8.3 the lone-admin protection lives in the service
layer (:mod:`romarr.auth.users`); the router translates its
``CannotDeleteLastAdminError`` to HTTP 409.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.api.routers.auth_schemas import UserPublic
from romarr.auth import Principal
from romarr.auth.users import (
    CannotDeleteLastAdminError,
    UserCreateError,
    create_password_reset_token,
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)

router = APIRouter(prefix="/api/v3/user", tags=["User"])


# ---------------------------------------------------------------------------
# Schemas (small enough to live inline)
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class CreateUserRequest(_Base):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[str | None, Field(min_length=8, max_length=255)] = None
    email: Annotated[str | None, Field(max_length=255)] = None
    role: Annotated[str, Field(pattern=r"^(?:admin|user|readonly)$")] = "user"
    is_active: bool = True


class UpdateUserRequest(_Base):
    role: Annotated[str | None, Field(pattern=r"^(?:admin|user|readonly)$")] = None
    email: Annotated[str | None, Field(max_length=255)] = None
    is_active: bool | None = None


class ResetTokenResponse(_Base):
    plaintext: str
    expires_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validation_400(exc: UserCreateError) -> HTTPException:
    """Translate a service-layer UserCreateError into HTTP 400."""
    code = getattr(exc, "code", "validation_failed")
    http_code = (
        status.HTTP_404_NOT_FOUND
        if code == "not_found"
        else status.HTTP_409_CONFLICT
        if code in ("username_taken", "email_taken")
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(
        status_code=http_code,
        detail={
            "errorMessage": code,
            "errorCode": code,
            "details": str(exc),
        },
    )


def _to_dict(user: Any) -> dict[str, Any]:
    """Pluck the columns we want from a User row for response models."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "preferences": user.preferences,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[UserPublic],
    summary="List every user (admin only). The id=0 system sentinel is hidden.",
)
async def list_users_endpoint(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserPublic]:
    rows = await list_users(db)
    return [UserPublic.model_validate(_to_dict(r)) for r in rows]


@router.post(
    "",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (admin only).",
)
async def create_user_endpoint(
    payload: CreateUserRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPublic:
    try:
        user = await create_user(
            db,
            username=payload.username,
            password=payload.password,
            email=payload.email,
            role=payload.role,
            is_active=payload.is_active,
        )
    except UserCreateError as exc:
        raise _validation_400(exc) from exc
    return UserPublic.model_validate(_to_dict(user))


@router.get(
    "/{user_id}",
    response_model=UserPublic,
    summary="Read a user by id (admin only).",
)
async def read_user_endpoint(
    user_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPublic:
    user = await get_user(db, user_id=user_id)
    if user is None or user.id == 0:
        # Hide the system sentinel from the API surface.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"errorMessage": "not_found", "errorCode": "not_found"},
        )
    return UserPublic.model_validate(_to_dict(user))


@router.put(
    "/{user_id}",
    response_model=UserPublic,
    summary="Update a user's role / email / active flag (admin only).",
)
async def update_user_endpoint(
    user_id: int,
    payload: UpdateUserRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPublic:
    try:
        user = await update_user(
            db,
            user_id=user_id,
            role=payload.role,
            email=payload.email,
            is_active=payload.is_active,
        )
    except CannotDeleteLastAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "cannot_delete_last_admin",
                "errorCode": "cannot_delete_last_admin",
                "details": str(exc),
            },
        ) from exc
    except UserCreateError as exc:
        raise _validation_400(exc) from exc
    return UserPublic.model_validate(_to_dict(user))


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user (admin only). Refuses the lone admin and the system sentinel.",
)
async def delete_user_endpoint(
    user_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        deleted = await delete_user(db, user_id=user_id)
    except CannotDeleteLastAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "cannot_delete_last_admin",
                "errorCode": "cannot_delete_last_admin",
                "details": str(exc),
            },
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"errorMessage": "not_found", "errorCode": "not_found"},
        )


@router.post(
    "/{user_id}/reset-password",
    response_model=ResetTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a one-time password-reset token (admin only).",
)
async def admin_reset_password(
    user_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ResetTokenResponse:
    """SMTP integration is out of scope at MVP — the admin shares the
    plaintext out-of-band (chat, sticky note, password manager).
    """
    try:
        result = await create_password_reset_token(db, user_id=user_id)
    except UserCreateError as exc:
        raise _validation_400(exc) from exc
    return ResetTokenResponse(plaintext=result.plaintext, expires_at=result.expires_at)
