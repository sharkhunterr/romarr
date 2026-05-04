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
    library_fk_column: str | None = None,
) -> APIRouter:
    """Build a CRUD router for one profile type.

    ``label`` flows into the not-found / duplicate error envelopes;
    keep it kebab-case (``quality-profile``, etc.) so error codes
    stay consistent with the URL slug.

    ``library_fk_column`` names the ``library.*_profile_id`` column
    that pins this profile type — e.g. ``"quality_profile_id"`` for
    QualityProfile. The DELETE handler walks the column to detect
    bound libraries and surfaces a 409 when ``?force=false``. When
    the column is not set (CustomFormat, today), the m2m
    ``library_custom_format.custom_format_id`` cascade rule on the
    spec 009 migration handles the bind automatically (FK
    ``ondelete=CASCADE``), so the DELETE just works.
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
            f"Delete a {label} (admin only). ``?force=true`` is a "
            "future-extension knob: today the cascade detection "
            "still 409s when the profile is bound, because the "
            "library.*_profile_id columns are NOT NULL — a force-"
            "unbind would require either a schema change to allow "
            "NULL or a 'substitute with factory default' rebind."
        ),
        responses={
            204: {"description": "Deleted."},
            404: {"description": "No row with this id."},
            409: {
                "description": (
                    "Profile is bound by one or more libraries. "
                    "Detail carries the blocking library names so "
                    "the operator can rebind manually."
                )
            },
        },
    )
    async def delete_row(
        row_id: int,
        _admin: Annotated[Principal, Depends(require_admin)],
        db: Annotated[AsyncSession, Depends(get_db)],
        force: Annotated[
            bool,
            Query(
                description=(
                    "Future-extension flag. The current cascade "
                    "implementation still 409s when bound (NOT NULL "
                    "FKs prevent NULL-out)."
                ),
            ),
        ] = False,
    ) -> Response:
        row = (
            await db.execute(select(model_cls).where(model_cls.id == row_id))
        ).scalar_one_or_none()
        if row is None:
            raise _not_found(label)

        # Cascade detection (T077). Walk the matching
        # library.*_profile_id column when one is configured.
        # CustomFormat is bound via the m2m library_custom_format
        # which has ondelete=CASCADE on the FK, so the DELETE just
        # works there without an explicit detection pass.
        if library_fk_column is not None:
            from romarr.libraries.models import Library

            fk_col = getattr(Library, library_fk_column)
            blocking_rows = (
                await db.execute(
                    select(Library.id, Library.name).where(fk_col == row_id)
                )
            ).all()
            if blocking_rows:
                blocking_names = [r[1] for r in blocking_rows]
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "errorMessage": f"{label}_in_use",
                        "errorCode": "in_use",
                        "details": (
                            f"{label} is bound by "
                            f"{len(blocking_rows)} library/libraries: "
                            f"{', '.join(blocking_names)}. Rebind "
                            "those libraries before deleting."
                        ),
                        "blocking_libraries": blocking_names,
                    },
                )

        # ``force`` is accepted on the surface for forward-
        # compatibility once a substitute-rebind semantic ships;
        # today it's a no-op because the NOT NULL FK schema
        # leaves the safe path identical to ``force=false``.
        del force

        try:
            await db.delete(row)
            await db.commit()
        except IntegrityError as exc:
            # Defence-in-depth: if a Library row was inserted
            # between the detection query and the commit (race),
            # the FK RESTRICT will raise here. Surface the same
            # 409 the detection branch would have.
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "errorMessage": f"{label}_in_use",
                    "errorCode": "in_use",
                    "details": "concurrent library binding prevents delete",
                },
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


__all__ = ["make_crud_router"]
