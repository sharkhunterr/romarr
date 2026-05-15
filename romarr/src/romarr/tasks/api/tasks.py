"""Tasks API — `/api/v3/system/tasks*` (T064-T072, FR-024-FR-026).

Routes:

  - GET    /api/v3/system/tasks             — list every job
  - GET    /api/v3/system/tasks/{job_id}    — single job
  - PATCH  /api/v3/system/tasks/{job_id}    — update schedule
                                              / enabled flags
                                              (admin)
  - POST   /api/v3/system/tasks/{job_id}/trigger
                                            — manual fire (admin)

The PATCH endpoint validates the schedule via the schema layer
(mutually-exclusive cron / interval, interval ≥ 30 s, FR-025)
and applies the new cadence via
``SchedulerService.reschedule_job`` so APScheduler picks it up
within 60 s without a restart (FR-026, SC-007). When no
``SchedulerService`` is wired into the app (no lifespan
integration yet), PATCH still updates the persisted ``Job``
row so a future scheduler bootstrap reads the right state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.tasks.errors import (
    JobAlreadyRunning,
    JobDisabled,
    ScheduleParseError,
    UnknownJob,
)
from romarr.tasks.models import Job, JobRun
from romarr.tasks.schemas import (
    JobRead,
    JobUpdate,
    TriggerRequest,
    TriggerResponse,
)
from romarr.tasks.types import JobStatus, TriggerKind

if TYPE_CHECKING:
    from romarr.tasks.scheduler import SchedulerService

router = APIRouter(prefix="/api/v3/system/tasks", tags=["Tasks"])


def _to_read(
    row: Job,
    *,
    current_run_id: int | None = None,
    current_run_items_processed: int | None = None,
) -> JobRead:
    """Build a :class:`JobRead` from the ORM row + the API-layer
    computed fields (``is_paused_by_health``, ``current_run_id``,
    ``current_run_items_processed``)."""
    payload = {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "schedule_cron": row.schedule_cron,
        "schedule_interval_seconds": row.schedule_interval_seconds,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at,
        "last_run_at": row.last_run_at,
        "last_run_duration_ms": row.last_run_duration_ms,
        "last_run_status": row.last_run_status,
        "last_error": row.last_error,
        "max_concurrent_instances": row.max_concurrent_instances,
        "max_retries": row.max_retries,
        "is_factory_default": row.is_factory_default,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        # Computed at the API layer; auto-pause integration lands
        # when the lifespan wiring threads HealthEngine through.
        "is_paused_by_health": False,
        "current_run_id": current_run_id,
        "current_run_items_processed": current_run_items_processed,
    }
    return JobRead.model_validate(payload)


def _scheduler(request: Request) -> SchedulerService | None:
    """Read the optional :class:`SchedulerService` off
    ``app.state``. None means the lifespan hasn't wired one yet
    — endpoints that depend on it surface 503 rather than
    crashing."""
    return getattr(request.app.state, "scheduler", None)


# ---------------------------------------------------------------------------
# CRUD (read + update)


@router.get("", response_model=list[JobRead])
async def list_tasks(
    _principal: Annotated[Principal, Depends(require_readonly)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[JobRead]:
    rows = (
        await session.execute(select(Job).order_by(Job.id))
    ).scalars().all()
    # Slice 474 — populate the ``current_run_id`` computed field
    # so the Activity active-tasks banner can detect jobs in
    # flight. One running run per job is the contract
    # (max_concurrent_instances defaults to 1); we pick the
    # newest just in case.
    running_runs = (
        await session.execute(
            select(
                JobRun.job_id,
                func.max(JobRun.id).label("run_id"),
            )
            .where(JobRun.status == JobStatus.RUNNING.value)
            .group_by(JobRun.job_id)
        )
    ).all()
    running_by_job: dict[str, int] = {
        row.job_id: row.run_id for row in running_runs
    }
    # Pull items_processed for those runs so the Activity banner
    # surfaces a live counter without a second round trip per
    # running job.
    items_by_run: dict[int, int] = {}
    if running_by_job:
        ids = list(running_by_job.values())
        items_rows = (
            await session.execute(
                select(JobRun.id, JobRun.items_processed).where(
                    JobRun.id.in_(ids)
                )
            )
        ).all()
        items_by_run = dict(items_rows)
    return [
        _to_read(
            row,
            current_run_id=running_by_job.get(row.id),
            current_run_items_processed=(
                items_by_run.get(running_by_job[row.id])
                if row.id in running_by_job
                else None
            ),
        )
        for row in rows
    ]


@router.get("/{job_id}", response_model=JobRead)
async def get_task(
    job_id: str,
    _principal: Annotated[Principal, Depends(require_readonly)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobRead:
    row = await session.get(Job, job_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="task not found",
        )
    return _to_read(row)


@router.patch("/{job_id}", response_model=JobRead)
async def patch_task(
    job_id: str,
    payload: JobUpdate,
    request: Request,
    _admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobRead:
    """Update schedule / concurrency / enabled. Admin-only.

    When a SchedulerService is wired and the schedule changed,
    ``reschedule_job`` is called so the new cadence applies
    within 60 s without a restart (FR-026)."""
    row = await session.get(Job, job_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="task not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    schedule_changed = (
        "schedule_cron" in update_data
        or "schedule_interval_seconds" in update_data
    )

    for field, value in update_data.items():
        setattr(row, field, value)

    # Validate the resulting schedule shape (mutually-exclusive
    # cron / interval, ≥ 30 s, FR-025).
    if schedule_changed:
        cron = row.schedule_cron
        interval = row.schedule_interval_seconds
        if (
            cron is not None
            and interval is not None
            and row.type != "auto_check_added"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "schedule_cron and schedule_interval_seconds "
                    "are mutually exclusive"
                ),
            )

    await session.commit()
    await session.refresh(row)

    scheduler = _scheduler(request)
    if scheduler is not None and schedule_changed:
        try:
            await scheduler.reschedule_job(
                job_id,
                cron=row.schedule_cron,
                interval_seconds=row.schedule_interval_seconds,
            )
        except UnknownJob:
            # Job not registered with the scheduler yet (e.g.
            # disabled at bootstrap). The persisted state is
            # correct; the next ``start()`` cycle will register.
            pass
        except ScheduleParseError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    return _to_read(row)


# ---------------------------------------------------------------------------
# Trigger (manual fire)


@router.post(
    "/{job_id}/trigger",
    response_model=TriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_task(
    job_id: str,
    payload: TriggerRequest | None,
    request: Request,
    admin: Annotated[Principal, Depends(require_admin)],
    force: bool = False,
) -> TriggerResponse:
    """Manually fire a job. Admin-only.

    The optional ``?force=true`` query bypasses the
    ``enabled=False`` gate (US5.2). Auto-pause is also
    bypassed for manual triggers — only scheduled cycles get
    the gate."""
    scheduler = _scheduler(request)
    if scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="scheduler not running",
        )

    parameters = (
        dict(payload.kwargs) if payload is not None else {}
    )
    user_id = getattr(admin, "user_id", None)

    try:
        run_id = await scheduler.trigger(
            job_id,
            triggered_by=TriggerKind.MANUAL,
            triggered_by_user_id=user_id,
            parameters=parameters,
            force=force,
        )
    except UnknownJob as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except JobDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except JobAlreadyRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return TriggerResponse(job_run_id=run_id)


__all__ = ["router"]
