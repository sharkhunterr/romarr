"""Shared CRUD router factory for the six profile endpoints.

Each profile type ships an APIRouter with the same six operations:

  * ``GET    {base}/schema``        — JSON Schema descriptor (auth)
  * ``GET    {base}``               — list (auth)
  * ``POST   {base}``               — create (admin)
  * ``GET    {base}/{id}``          — read (auth)
  * ``PUT    {base}/{id}``          — partial update (admin)
  * ``DELETE {base}/{id}``          — delete with optional ``?force=true`` (admin)

Per FR-032a: reads are accessible to any authenticated user (the
``require_readonly`` guard); mutations + the naming-preview endpoint
require the admin role.

The factory builds one router per profile type; each call is
self-contained so FastAPI's runtime introspection of ``Annotated[T,
Depends(...)]`` works without sharing closures between routers. Six
near-identical wirings is more code than a single generic
``Router[T]`` would be, but it's far easier to debug — every endpoint
shows up explicitly in the OpenAPI surface.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.profiles.errors import ProfileError


def _flag_user_modified(row: Any) -> None:
    """Stamp the FR-003a sentinel on any operator mutation."""
    if hasattr(row, "is_user_modified"):
        row.is_user_modified = True


def _maybe_409_conflict(exc: IntegrityError, *, label: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "errorMessage": f"duplicate_{label}",
            "errorCode": "duplicate",
            "details": (
                f"a {label} with the same name already exists"
            ),
        },
    )


def _not_found(label: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "errorMessage": f"{label}_not_found",
            "errorCode": "not_found",
        },
    )


def make_crud_router(
    *,
    label: str,
    base_path: str,
    tag: str,
    model_cls: type[Any],
    schema_read: type[BaseModel],
    schema_create: type[BaseModel],
    schema_update: type[BaseModel],
) -> APIRouter:
    """Build a CRUD router for one profile type.

    ``label`` flows into the not-found / duplicate error envelopes;
    keep it kebab-case (``quality-profile``, etc.) so error codes
    stay consistent with the URL slug.
    """
    router = APIRouter(prefix=base_path, tags=[tag])

    # ---- /schema (must be registered BEFORE /{id} to avoid the path
    # collision where ``schema`` is parsed as an integer id). --------

    @router.get(
        "/schema",
        summary=f"JSON Schema descriptor for {label} (any authenticated user).",
    )
    async def get_schema(
        _user: Annotated[Principal, Depends(require_readonly)],
    ) -> dict[str, Any]:
        return TypeAdapter(schema_read).json_schema()

    # ---- list / read --------------------------------------------------

    @router.get(
        "",
        response_model=list[schema_read],  # type: ignore[valid-type]
        summary=f"List {label} (any authenticated user).",
    )
    async def list_rows(
        _user: Annotated[Principal, Depends(require_readonly)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> list[Any]:
        rows = (
            (await db.execute(select(model_cls).order_by(model_cls.id)))
            .scalars()
            .all()
        )
        return [schema_read.model_validate(r, from_attributes=True) for r in rows]

    @router.get(
        "/{row_id}",
        response_model=schema_read,
        summary=f"Read one {label} (any authenticated user).",
    )
    async def read_row(
        row_id: int,
        _user: Annotated[Principal, Depends(require_readonly)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> Any:
        row = (
            await db.execute(select(model_cls).where(model_cls.id == row_id))
        ).scalar_one_or_none()
        if row is None:
            raise _not_found(label)
        return schema_read.model_validate(row, from_attributes=True)

    # ---- create / update / delete (admin) -----------------------------

    @router.post(
        "",
        response_model=schema_read,
        status_code=status.HTTP_201_CREATED,
        summary=f"Create a {label} (admin only).",
    )
    async def create_row(
        body: Annotated[dict[str, Any], Body()],
        _admin: Annotated[Principal, Depends(require_admin)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> Any:
        try:
            payload = schema_create.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.errors(),
            ) from exc
        except ProfileError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "errorMessage": "profile_validation_failed",
                    "errorCode": "profile_validation",
                    "details": str(exc),
                },
            ) from exc
        row = model_cls(**payload.model_dump(by_alias=False))
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise _maybe_409_conflict(exc, label=label) from exc
        await db.refresh(row)
        return schema_read.model_validate(row, from_attributes=True)

    @router.put(
        "/{row_id}",
        response_model=schema_read,
        summary=f"Update a {label} (admin only). Flips is_user_modified=true.",
    )
    async def update_row(
        row_id: int,
        body: Annotated[dict[str, Any], Body()],
        _admin: Annotated[Principal, Depends(require_admin)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> Any:
        try:
            payload = schema_update.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.errors(),
            ) from exc
        row = (
            await db.execute(select(model_cls).where(model_cls.id == row_id))
        ).scalar_one_or_none()
        if row is None:
            raise _not_found(label)

        fields = payload.model_dump(exclude_unset=True, by_alias=False)
        for key, value in fields.items():
            setattr(row, key, value)
        _flag_user_modified(row)

        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise _maybe_409_conflict(exc, label=label) from exc
        await db.refresh(row)
        return schema_read.model_validate(row, from_attributes=True)

    @router.delete(
        "/{row_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary=(
            f"Delete a {label} (admin only). ``?force=true`` unbinds "
            "from libraries first."
        ),
    )
    async def delete_row(
        row_id: int,
        _admin: Annotated[Principal, Depends(require_admin)],
        db: Annotated[AsyncSession, Depends(get_db)],
        force: Annotated[bool, Query(description="Unbind from libraries first")] = False,
    ) -> Response:
        row = (
            await db.execute(select(model_cls).where(model_cls.id == row_id))
        ).scalar_one_or_none()
        if row is None:
            raise _not_found(label)
        # Spec 009 introduces the Library FK columns; today the gate
        # is a no-op because no library row can yet pin a profile.
        # ``force`` is accepted on the surface so spec 009 lights it
        # up without a breaking API change.
        del force  # surface contract — used once spec 009 lands
        await db.delete(row)
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


__all__ = ["make_crud_router"]
