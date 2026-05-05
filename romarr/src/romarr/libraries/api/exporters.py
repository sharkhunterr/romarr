"""Exporter catalog + manual-run endpoints (slice 279 / spec 009 T082).

  * GET  /api/v3/rom/exporters             — list available exporters
  * GET  /api/v3/rom/exporters/{name}      — single exporter descriptor
  * POST /api/v3/rom/exporters/{name}/run  — materialize + write the
    per-platform exporter file for one (library, platform_slug) pair

ESDE is the first exporter wired through ``POST /run`` (T078); the
Pegasus / LaunchBox / RomM materializers follow the same pattern
and land with their respective slices.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.libraries.exporters.esde import (
    render_gamelist_xml,
    write_gamelist_atomic,
)
from romarr.libraries.exporters._materialize import materialize_esde_games
from romarr.libraries.exporters.registry import (
    ExporterDescriptor,
    get_exporter,
    list_exporters,
)
from romarr.libraries.models import Library


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ExporterRead(_Base):
    """One exporter row in the catalog."""

    name: str
    description: str
    format: Literal["xml", "txt", "http"]
    available: bool


def _to_read(d: ExporterDescriptor) -> ExporterRead:
    return ExporterRead(
        name=d.name,
        description=d.description,
        format=d.format,
        available=d.available,
    )


router = APIRouter(prefix="/api/v3/rom/exporters", tags=["Exporters"])


@router.get(
    "",
    response_model=list[ExporterRead],
    summary="List the exporter catalog (any authenticated user).",
)
async def list_exporters_endpoint(
    _user: Annotated[Principal, Depends(require_readonly)],
) -> list[ExporterRead]:
    """Return the static catalog of exporters Romarr ships.

    Per-import dispatch + last-run tracking are deferred — this
    endpoint surfaces metadata only so the Settings UI can render
    an operator-visible list with descriptions + on-disk format
    hints.
    """
    return [_to_read(d) for d in list_exporters()]


@router.get(
    "/{name}",
    response_model=ExporterRead,
    summary="Read one exporter descriptor.",
    responses={
        404: {
            "description": "Unknown exporter name.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "errorMessage": "exporter_not_found",
                            "errorCode": "exporter_not_found",
                        }
                    }
                }
            },
        },
    },
)
async def read_exporter(
    name: str,
    _user: Annotated[Principal, Depends(require_readonly)],
) -> ExporterRead:
    descriptor = get_exporter(name)
    if descriptor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "exporter_not_found",
                "errorCode": "exporter_not_found",
            },
        )
    return _to_read(descriptor)


class ExporterRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_id: int = Field(ge=1)
    platform_slug: str = Field(min_length=1, max_length=64)


class ExporterRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    library_id: int
    platform_slug: str
    games_written: int
    written: bool
    """``False`` when the advisory lock was held by another writer
    (the writer coalesces — see :func:`write_gamelist_atomic`)."""


@router.post(
    "/{name}/run",
    response_model=ExporterRunResponse,
    summary="Materialize + write the exporter file (admin only).",
    responses={
        404: {"description": "Unknown exporter / library / platform."},
        409: {
            "description": (
                "Exporter is disabled for this library "
                "(``exporter_<name>_enabled=False``)."
            ),
        },
        501: {
            "description": (
                "Exporter is documented but its run path isn't wired "
                "yet. Today only ``esde`` is wired."
            )
        },
    },
)
async def run_exporter(
    name: str,
    body: Annotated[ExporterRunRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExporterRunResponse:
    """T078 — run one exporter on demand for a (library, platform).

    The endpoint refuses when the exporter's per-library enable
    flag is False so the manual-run can't bypass the operator's
    opt-out. ESDE is the only exporter wired today; pegasus /
    launchbox / romm return 501 with a clear marker until their
    materializers ship.
    """
    descriptor = get_exporter(name)
    if descriptor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "exporter_not_found",
                "errorCode": "exporter_not_found",
            },
        )

    library = await db.get(Library, body.library_id)
    if library is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "library_not_found",
                "errorCode": "library_not_found",
            },
        )

    if name != "esde":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "errorMessage": "exporter_run_not_wired",
                "errorCode": "exporter_run_not_wired",
            },
        )

    if not library.exporter_esde_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "exporter_disabled_on_library",
                "errorCode": "exporter_disabled_on_library",
            },
        )

    games = await materialize_esde_games(
        session=db,
        library_id=body.library_id,
        platform_slug=body.platform_slug,
    )
    target_dir = Path(library.path) / body.platform_slug
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    xml_bytes = render_gamelist_xml(games)
    try:
        written = write_gamelist_atomic(target_dir, xml_bytes)
        run_status = "ok" if written else "coalesced"
        run_error = None
    except Exception as exc:
        written = False
        run_status = "error"
        run_error = str(exc)

    # T077 / FR-019 — track emission for operator visibility.
    from romarr.libraries.exporters._runs import record_exporter_run

    await record_exporter_run(
        session=db,
        library_id=body.library_id,
        exporter_name="esde",
        status=run_status,
        error=run_error,
    )

    if run_status == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "errorMessage": "exporter_run_failed",
                "errorCode": "exporter_run_failed",
                "details": run_error,
            },
        )

    return ExporterRunResponse(
        name=name,
        library_id=body.library_id,
        platform_slug=body.platform_slug,
        games_written=len(games),
        written=written,
    )


class LibraryExporterRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    library_id: int
    exporter_name: str
    last_run_at: object | None = None
    run_count: int
    last_status: str
    last_error: str | None = None


@router.get(
    "/runs/{library_id}",
    response_model=list[LibraryExporterRunRead],
    summary="Per-(library, exporter) emission tracking (any user).",
)
async def list_library_exporter_runs(
    library_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LibraryExporterRunRead]:
    """T077 / FR-019 — return the per-exporter run rows for one
    library. Empty list when no exporter has fired yet."""
    from sqlalchemy import select as _select

    from romarr.libraries.models import LibraryExporterRun

    rows = (
        await db.execute(
            _select(LibraryExporterRun)
            .where(LibraryExporterRun.library_id == library_id)
            .order_by(LibraryExporterRun.exporter_name)
        )
    ).scalars().all()
    return [LibraryExporterRunRead.model_validate(r) for r in rows]


__all__ = ["router"]
