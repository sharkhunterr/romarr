"""Scan trigger endpoints (spec 009 T076 + T081 — POST scan).

Two routes covering FR-009 manual rescan triggers:

  * POST ``/api/v3/rom/library/{id}/scan`` — rescan ONE library.
  * POST ``/api/v3/rom/scan`` — rescan EVERY enabled library.

Both delegate to :class:`SchedulerService.trigger` for the
``LibraryScan`` job (see :class:`LibraryScanAdapter`). The adapter
runs ``full_scan`` per library; ``libraryId`` parameter scopes a
single-library run. The Sonarr-compat ``POST /api/v3/command``
endpoint already accepts ``RescanLibrary`` for the same effect —
these dedicated routes mirror Radarr/Sonarr's REST style for
operators who prefer URL-scoped actions over the command bus.

Returns the new ``JobRun.id`` in the Sonarr-shape ``CommandStatus``
envelope (mirrors :mod:`romarr.tasks.api.command`) so the UI
polls progress with the same code path as command-bus calls.

Admin-gated: triggering a scan is a privileged operation per
Article XII (privileged trigger surface — same rationale as the
notification test endpoint and the command bus).
"""

from __future__ import annotations

from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.libraries.models import Library
from romarr.tasks.errors import (
    JobAlreadyRunning,
    JobDisabled,
    UnknownJob,
)
from romarr.tasks.models import JobRun
from romarr.tasks.types import JobStatus, TriggerKind

router = APIRouter(prefix="/api/v3/rom", tags=["Library"])


_SCAN_JOB_ID = "LibraryScan"


def _scheduler(request: Request) -> Any:
    return getattr(request.app.state, "scheduler", None)


def _serialise_run(run: JobRun) -> dict[str, Any]:
    """Sonarr-shape ``CommandStatus`` envelope for a JobRun.

    Mirrors :func:`romarr.tasks.api.command._serialise_command_status`
    so the UI's polling code path works against either trigger
    surface without translation.
    """
    started = run.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    ended = run.finished_at
    if ended is not None and ended.tzinfo is None:
        ended = ended.replace(tzinfo=UTC)
    return {
        "id": run.id,
        "name": run.job_id,
        "status": run.status.value
        if isinstance(run.status, JobStatus)
        else str(run.status),
        "queued": started.isoformat(),
        "started": started.isoformat(),
        "ended": ended.isoformat() if ended is not None else None,
        "trigger": run.triggered_by.value
        if isinstance(run.triggered_by, TriggerKind)
        else str(run.triggered_by),
        "stateChangeTime": started.isoformat(),
    }


async def _trigger_scan(
    *,
    request: Request,
    admin: Principal,
    parameters: dict[str, Any] | None,
) -> dict[str, Any]:
    scheduler = _scheduler(request)
    if scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "errorMessage": "scheduler not running",
                "errorCode": "scheduler_unavailable",
            },
        )

    try:
        run_id = await scheduler.trigger(
            _SCAN_JOB_ID,
            triggered_by=TriggerKind.MANUAL,
            triggered_by_user_id=getattr(admin, "user_id", None),
            parameters=parameters or {},
        )
    except UnknownJob as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": str(exc),
                "errorCode": "unknown_job",
            },
        ) from exc
    except JobDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": str(exc),
                "errorCode": "job_disabled",
            },
        ) from exc
    except JobAlreadyRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": str(exc),
                "errorCode": "job_already_running",
            },
        ) from exc

    sm = request.app.state.db_sessionmaker
    async with sm() as session:
        run = await session.get(JobRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "errorMessage": "scan row vanished",
                    "errorCode": "server_error",
                },
            )
        return _serialise_run(run)


@router.post(
    "/scan",
    status_code=status.HTTP_201_CREATED,
)
async def post_scan_all(
    request: Request,
    admin: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    """Trigger a full scan across every enabled library."""
    return await _trigger_scan(
        request=request, admin=admin, parameters=None
    )


@router.post(
    "/library/{library_id}/scan",
    status_code=status.HTTP_201_CREATED,
)
async def post_scan_library(
    library_id: int,
    request: Request,
    admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Trigger a full scan against a single library."""
    library = (
        await session.execute(
            select(Library).where(Library.id == library_id)
        )
    ).scalar_one_or_none()
    if library is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"library {library_id} not found",
                "errorCode": "library_not_found",
            },
        )
    return await _trigger_scan(
        request=request,
        admin=admin,
        parameters={"libraryId": library_id},
    )


__all__ = ["router"]
