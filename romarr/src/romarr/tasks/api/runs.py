"""JobRun history + cancel endpoints (T069, T073).

Routes:

  - GET    /api/v3/system/tasks/{job_id}/runs
                                  — paginated history with
                                    ``status`` / ``triggered_by``
                                    filters
  - POST   /api/v3/system/tasks/{job_id}/runs/{run_id}/cancel
                                  — admin-only; signals the
                                    cooperative cancellation
                                    event and returns once
                                    the runner has reached a
                                    terminal state (or after
                                    the force-terminate window
                                    fires).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.tasks.models import Job, JobRun
from romarr.tasks.schemas import JobRunRead

if TYPE_CHECKING:
    from romarr.tasks.execution.cancellation import CancellationRegistry

router = APIRouter(prefix="/api/v3/system/tasks", tags=["Tasks"])


def _cancellation_registry(
    request: Request,
) -> CancellationRegistry | None:
    return getattr(request.app.state, "cancellation_registry", None)


@router.get(
    "/{job_id}/runs",
    response_model=list[JobRunRead],
)
async def list_runs(
    job_id: str,
    _principal: Annotated[Principal, Depends(require_readonly)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            description=(
                "Filter by terminal status — "
                "running / success / failed / partial / cancelled"
            ),
        ),
    ] = None,
    triggered_by: Annotated[
        str | None,
        Query(
            description=(
                "Filter by trigger kind — "
                "scheduled / manual / command / event"
            ),
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobRunRead]:
    """Paginated job-run history. ``status`` + ``triggered_by``
    filters compose. Default sort is ``started_at DESC`` so the
    most recent runs land first."""
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="task not found",
        )

    stmt = select(JobRun).where(JobRun.job_id == job_id)
    if status_filter is not None:
        stmt = stmt.where(JobRun.status == status_filter)
    if triggered_by is not None:
        stmt = stmt.where(JobRun.triggered_by == triggered_by)
    stmt = stmt.order_by(JobRun.started_at.desc()).offset(offset).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return [JobRunRead.model_validate(row) for row in rows]


@router.post(
    "/{job_id}/runs/{run_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_run(
    job_id: str,
    run_id: int,
    request: Request,
    _admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """Cancel an in-flight job_run. Admin-only.

    Returns 202 with ``{"forced": bool}`` reflecting whether
    the runner cooperated within the configured window or had
    to be force-terminated. 404 if the run doesn't exist or
    has already completed; 409 if the job_id doesn't match the
    run's parent (defensive — the run_id should be unique
    process-wide, but the path includes job_id for the
    REST-y reading).
    """
    run = await session.get(JobRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="run not found",
        )
    if run.job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "run does not belong to the requested job"
            ),
        )
    if run.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run already in terminal state: {run.status}",
        )

    registry = _cancellation_registry(request)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="cancellation registry not running",
        )

    cancelled = await registry.cancel(run_id)
    if not cancelled:
        # The run wasn't registered (e.g. wrong replica or the
        # task already completed between the DB read and the
        # registry lookup). Surface 404 — operator UI retry is
        # safe.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="run is not in-flight on this replica",
        )

    # Re-read the row so the returned ``forced`` flag reflects
    # whether ``cancellation_forced`` was set during the cancel
    # protocol (force-terminate path).
    await session.refresh(run)
    return {
        "job_run_id": run_id,
        "status": run.status,
        "forced": bool(run.cancellation_forced),
    }


__all__ = ["router"]
