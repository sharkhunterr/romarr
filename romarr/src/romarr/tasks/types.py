"""Value types for the tasks/scheduler subsystem (spec 012).

These are the in-memory shapes the scheduler service threads
through one job-run lifecycle. Persistence shapes (Job, JobRun)
live in :mod:`romarr.tasks.models`; what's here is the working
memory the runner protocol receives from the lifecycle helper.

Frozen-by-default Pydantic models — once a runner starts, the
context shouldn't mutate behind it. The two exceptions are
``JobContext.kwargs`` (operator-supplied parameters for
parameterised jobs) and ``JobResult`` (the runner's return
value); both pass through the lifecycle helper which writes
the persisted form.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums


class JobStatus(StrEnum):
    """Terminal + transient states a job_run can be in.

    ``RUNNING`` is the initial value the lifecycle helper writes;
    every run MUST transition to one of the four terminal states
    when the runner returns or shutdown forces it.
    """

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class TriggerKind(StrEnum):
    """How the run was started — audit attribution column."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    COMMAND = "command"
    EVENT = "event"


# ---------------------------------------------------------------------------
# Job context (runner input)


class JobContext(BaseModel):
    """Everything a runner needs for one execution.

    The progress callback throttles to ~10 events/sec at the
    execution-helper layer; runners can call it at every
    sub-step boundary without worrying about overwhelming the
    WebSocket channel. The cancellation event is set by the
    shutdown handler; runners that ``await
    cancellation_event.wait()`` return cooperatively before the
    5-second force-terminate kicks in.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    job_id: str
    job_run_id: int
    started_at: datetime
    triggered_by: TriggerKind
    triggered_by_user_id: int | None = None
    progress_callback: Callable[[int, int, str], None]
    cancellation_event: asyncio.Event
    parameters: dict[str, Any] = Field(default_factory=dict)
    # Slice 210 — adapters that need to do real DB work (the
    # scheduler-wired ones in ``adapters.py``) read this off
    # the context with ``getattr(context, "sessionmaker",
    # None)``; the scheduler threads its session_factory
    # through here. Stays optional so existing tests that
    # build a JobContext without the field keep working.
    sessionmaker: Any = None
    # Slice 277 — optional EventChannel reference. When wired,
    # runners (DatUpdate / future) publish their per-event
    # payloads through it (``OnDatUpdate`` / etc.) and the WS
    # bridge fans out to live operator sessions automatically.
    # Tests build a JobContext without this field; runners
    # short-circuit emission when None.
    event_channel: Any = None


class JobResult(BaseModel):
    """Runner return value. The lifecycle helper merges this
    into the persisted ``job_run`` row before transitioning
    ``status`` to terminal.
    """

    model_config = ConfigDict(frozen=True)

    status: JobStatus
    items_processed: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Sonarr-compat command shapes (spec 013 mounts these onto /api/v3/command)


class CommandPayload(BaseModel):
    """Body of a Sonarr-format ``POST /api/v3/command`` request.

    ``name`` is the runner's job_id (e.g. ``MissingSearch``,
    ``RefreshGame``); ``extra_kwargs`` mirrors Sonarr's per-
    command parameter blob (gameId, libraryId, etc.).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    extra_kwargs: dict[str, Any] = Field(default_factory=dict)


class CommandStatus(BaseModel):
    """Sonarr-format response for ``GET /api/v3/command/{id}``.

    Field names match Sonarr's camelCase JSON exactly so
    Notifiarr / Homepage poll Romarr's command queue without
    a translation layer.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: int
    name: str
    status: JobStatus
    started: datetime
    ended: datetime | None = None
    duration_ms: int | None = None
    triggered_by: str = Field(alias="triggeredBy")
    body: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "CommandPayload",
    "CommandStatus",
    "JobContext",
    "JobResult",
    "JobStatus",
    "TriggerKind",
]
