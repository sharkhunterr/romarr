"""Sonarr-compat command endpoint (T063, T088, FR-016, FR-017).

Routes:

  - POST   /api/v3/command          — fire a command by name
                                      (admin)
  - GET    /api/v3/command/{id}     — read command status
                                      (any auth role)
  - DELETE /api/v3/command/{id}     — cancel an in-flight
                                      command (admin)

The POST handler accepts Sonarr's payload shape:
``{"name": "<CommandName>", ...optional camelCase kwargs}``.
The optional kwargs are forwarded only if they're in the
alias's ``allowed_kwargs`` whitelist — unknown keys are
silently dropped (matches Sonarr's permissive behaviour).

The GET handler reads the underlying ``JobRun`` row and
serialises it to Sonarr's ``CommandStatus`` shape. Field
names match Sonarr's camelCase exactly so Notifiarr +
Homepage poll Romarr's command queue without a translation
layer.

The DELETE handler is the spec-013 unified cancel surface:
delegates to spec 012's :class:`CancellationRegistry`. Same
two-phase semantics as the runs endpoint
(``POST /api/v3/system/tasks/{job_id}/runs/{run_id}/cancel``):
cooperative event signal first, force-terminate after the
configured window. Returns 202 with the resolved ``forced``
flag.

Admin-gated for POST and DELETE per Article XII (privileged
trigger / cancel surface — same SSRF rationale as the
notification test endpoint). GET is reads, so any
authenticated role suffices.
"""

from __future__ import annotations

from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.tasks.command_aliases import (
    UnknownCommand,
    known_command_names,
    resolve_command,
)
from romarr.tasks.errors import (
    JobAlreadyRunning,
    JobDisabled,
    UnknownJob,
)
from romarr.tasks.models import JobRun
from romarr.tasks.types import JobStatus, TriggerKind

router = APIRouter(prefix="/api/v3/command", tags=["Tasks"])


def _scheduler(request: Request) -> Any:
    return getattr(request.app.state, "scheduler", None)


def _cancellation_registry(request: Request) -> Any:
    return getattr(request.app.state, "cancellation_registry", None)


def _serialise_command_status(run: JobRun) -> dict[str, Any]:
    """Build the Sonarr-shape ``CommandStatus`` dict from a
    ``JobRun`` row. The shape mirrors Sonarr's camelCase JSON
    so consumers don't need a translation layer."""
    started = run.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    ended = run.finished_at
    if ended is not None and ended.tzinfo is None:
        ended = ended.replace(tzinfo=UTC)

    state_map = {
        JobStatus.RUNNING.value: "started",
        JobStatus.SUCCESS.value: "completed",
        JobStatus.FAILED.value: "failed",
        JobStatus.PARTIAL.value: "completed",
        JobStatus.CANCELLED.value: "aborted",
    }

    return {
        "id": run.id,
        "name": run.job_id,
        "commandName": run.job_id,
        "status": state_map.get(run.status, run.status),
        "started": started.isoformat(),
        "ended": ended.isoformat() if ended is not None else None,
        "duration": run.duration_ms,
        "triggeredBy": run.triggered_by,
        "body": run.output_summary or {},
        "lastExecutionTime": (
            ended.isoformat() if ended is not None else None
        ),
    }


@router.get("/_known", response_model=list[str])
async def list_known_commands(
    _principal: Annotated[Principal, Depends(require_readonly)],
) -> list[str]:
    """Return the list of recognised Sonarr command names.
    Useful for the operator UI's discoverability."""
    return list(known_command_names())


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_command(
    payload: dict[str, Any],
    request: Request,
    admin: Annotated[Principal, Depends(require_admin)],
) -> dict[str, Any]:
    """Fire a Sonarr-shaped command. Admin-only.

    The payload's ``name`` field maps to a Romarr ``job_id``
    via :func:`resolve_command`. Optional camelCase kwargs
    (``gameId``, ``libraryId``) are forwarded as
    ``JobContext.parameters``.
    """
    name = payload.get("name") if isinstance(payload, dict) else None
    if not isinstance(name, str) or not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "command name is required",
                "errorCode": "invalid_command",
            },
        )

    try:
        job_id, parameters = resolve_command(
            name=name, payload=payload
        )
    except UnknownCommand as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": str(exc),
                "errorCode": "unknown_command",
            },
        ) from exc

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
            job_id,
            triggered_by=TriggerKind.COMMAND,
            triggered_by_user_id=getattr(admin, "user_id", None),
            parameters=parameters,
            # The operator clicked a button — honour the request
            # even when the job's scheduled cadence is disabled.
            # The ``enabled`` flag gates the cron/interval ticks;
            # explicit commands bypass it (slice 471).
            force=True,
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

    # Read the freshly-inserted JobRun row to build the Sonarr
    # response.
    sm = request.app.state.db_sessionmaker
    async with sm() as session:
        run = await session.get(JobRun, run_id)
        if run is None:
            # Defensive — the row was just inserted.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "errorMessage": "command row vanished",
                    "errorCode": "server_error",
                },
            )
        return _serialise_command_status(run)


@router.get("/{command_id}")
async def get_command_status(
    command_id: int,
    _principal: Annotated[Principal, Depends(require_readonly)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Read a command's status by id (= ``job_run.id``)."""
    run = await session.get(JobRun, command_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "command not found",
                "errorCode": "not_found",
            },
        )
    return _serialise_command_status(run)


@router.delete(
    "/{command_id}",
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_command(
    command_id: int,
    request: Request,
    _admin: Annotated[Principal, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Cancel an in-flight command. Admin-only.

    Mirrors the runs-endpoint contract: 404 if the command
    doesn't exist; 409 if it's already in a terminal state;
    503 if no cancellation registry is wired (scheduler off).
    Otherwise delegates to spec 012's
    :class:`CancellationRegistry` for the two-phase cooperative
    cancel + force-terminate protocol and returns 202 with the
    resolved ``forced`` flag.
    """
    run = await session.get(JobRun, command_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "command not found",
                "errorCode": "not_found",
            },
        )
    if run.status != JobStatus.RUNNING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": (
                    f"command already in terminal state: {run.status}"
                ),
                "errorCode": "command_terminal",
            },
        )

    registry = _cancellation_registry(request)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "errorMessage": "cancellation registry not running",
                "errorCode": "cancellation_unavailable",
            },
        )

    cancelled = await registry.cancel(command_id)
    if not cancelled:
        # The run wasn't registered (already finished, wrong
        # replica, race with the lifecycle helper). Surface
        # 404 — operator UI retry is safe.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": (
                    "command is not in-flight on this replica"
                ),
                "errorCode": "not_found",
            },
        )

    # Re-read so ``forced`` reflects the cancel-protocol outcome.
    await session.refresh(run)
    return {
        "id": command_id,
        "status": run.status,
        "forced": bool(run.cancellation_forced),
    }


__all__ = ["router"]
