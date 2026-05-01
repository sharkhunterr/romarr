"""Sonarr-compat command endpoint (T063, FR-016, FR-017).

Routes:

  - POST /api/v3/command          — fire a command by name
                                    (admin)
  - GET  /api/v3/command/{id}     — read command status
                                    (any auth role)

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

Admin-gated for POST per Article XII (the command endpoint
is a privileged trigger surface — same SSRF rationale as the
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


__all__ = ["router"]
