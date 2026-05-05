"""Exporter catalog + manual-run endpoints (slice 279 / spec 009 T082).

  * GET  /api/v3/rom/exporters             — list available exporters
  * GET  /api/v3/rom/exporters/{name}      — single exporter descriptor

Per-import dispatch + ``POST /exporters/{name}/run`` (T078) land
when the spec 008 importer's per-import fan-out arrives — at that
point each exporter knows how to materialise itself for one
(library, platform_slug) pair, and the run endpoint becomes a thin
wrapper around the importer's helper.

Today's surface is read-only metadata so the Settings UI can
render the operator-facing list with descriptions + format hints.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from romarr.api.dependencies import require_readonly
from romarr.auth import Principal
from romarr.libraries.exporters.registry import (
    ExporterDescriptor,
    get_exporter,
    list_exporters,
)


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


__all__ = ["router"]
