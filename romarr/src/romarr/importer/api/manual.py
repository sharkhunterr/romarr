"""Manual import + retry endpoints (spec 008 — HARD/T088).

  * POST ``/api/v3/rom/import/manual``    — bulk import per
    operator decisions; thin REST surface over
    :func:`romarr.importer.orchestrator.run_import`.
  * POST ``/api/v3/rom/import/retry/{id}`` — re-trigger
    ``run_import`` against the source path of a previously-
    failed ``import_history`` row. The original row is
    preserved; a new row is created (FR-035 — every retry is
    independently auditable).

Both routes admin-gated per FR-033a (privileged-trigger
surface, same rationale as the manual-match endpoint).

Path-divergence note: the spec 009 surface
``POST /api/v3/rom/manual-import`` ships the bulk-listing
flow (folder browse → bulk POST). These spec 008 routes
target the per-file-with-game-id and retry surfaces — the
two are complementary rather than competing. The Sonarr
clones (Notifiarr, Homepage) drive the spec 008 routes; the
operator UI's "browse a folder + import what I want" flow
uses spec 009.
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.importer.models import ImportHistory
from romarr.importer.orchestrator import run_import
from romarr.importer.schemas import (
    ImportHistoryRead,
    ManualImportRequest,
    RetryResponse,
)
from romarr.importer.types import ImportContext

router = APIRouter(prefix="/api/v3/rom/import", tags=["Importer"])


def _to_history_read(row: ImportHistory) -> ImportHistoryRead:
    """Translate an ImportHistory ORM row → wire shape."""
    return ImportHistoryRead.model_validate(row, from_attributes=True)


@router.post(
    "/manual",
    response_model=list[ImportHistoryRead],
    status_code=status.HTTP_200_OK,
)
async def post_import_manual(
    payload: ManualImportRequest,
    request: Request,
    admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ImportHistoryRead]:
    """Bulk manual import — admin-only.

    Each entry is dispatched to ``run_import`` with a fresh
    correlation id; the response carries the resulting
    ``import_history`` row per entry. Per-entry exceptions are
    isolated (one failure doesn't drop the batch).
    """
    sm = request.app.state.db_sessionmaker
    histories: list[ImportHistory] = []
    imported_by = getattr(admin, "username", None) or "manual"

    for entry in payload.entries:
        path = Path(entry.path) if not isinstance(entry.path, Path) else entry.path
        context = ImportContext(
            source_path=path,
            correlation_id=uuid4(),
            imported_via="manual",
            imported_by=imported_by,
            force=entry.force,
        )
        try:
            async with sm() as inner_session:
                outcome = await run_import(context, session=inner_session)
            row = await session.get(ImportHistory, outcome.history_id)
            if row is not None:
                histories.append(row)
        except Exception:  # noqa: BLE001 — per-entry isolation
            continue

    return [_to_history_read(row) for row in histories]


@router.post(
    "/retry/{import_history_id}",
    response_model=RetryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_import_retry(
    import_history_id: int,
    request: Request,
    admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RetryResponse:
    """Retry a previously-imported file.

    Looks up the original ``import_history`` row, replays
    ``run_import`` against its ``source_path`` with a fresh
    correlation id. Returns the freshly-created
    ``import_history`` row; the original is preserved
    (FR-035).
    """
    original = await session.get(ImportHistory, import_history_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": (
                    f"import_history {import_history_id} not found"
                ),
                "errorCode": "import_history_not_found",
            },
        )
    if not original.source_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "original row has no source_path",
                "errorCode": "no_source_path",
            },
        )

    sm = request.app.state.db_sessionmaker
    imported_by = getattr(admin, "username", None) or "manual"
    context = ImportContext(
        source_path=Path(original.source_path),
        correlation_id=uuid4(),
        imported_via=original.imported_via or "manual",
        imported_by=imported_by,
        force=False,
    )
    async with sm() as inner_session:
        outcome = await run_import(context, session=inner_session)

    new_row = await session.get(ImportHistory, outcome.history_id)
    if new_row is None:  # pragma: no cover — defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "errorMessage": "retry produced no history row",
                "errorCode": "server_error",
            },
        )
    return RetryResponse(history=_to_history_read(new_row))


__all__ = ["router"]
