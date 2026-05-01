"""Domain errors for the tasks/scheduler subsystem (spec 012).

Domain-specific names per Article XII; ``noqa: N818`` markers
acknowledge the diverged ``…Error`` convention where the name
reads more naturally on call sites.
"""

from __future__ import annotations


class TaskError(Exception):
    """Base class for every domain-level task scheduler failure."""


class JobAlreadyRunning(TaskError):  # noqa: N818
    """Raised when an operator triggers a job whose
    ``max_concurrent_instances`` cap is already at limit. The API
    layer maps this to HTTP 409 Conflict so the operator's UI can
    refuse the trigger without retrying."""


class JobDisabled(TaskError):  # noqa: N818
    """Raised when an operator triggers a job whose ``enabled``
    flag is False. Auto-paused jobs (FR-019) raise this too;
    the API layer maps to HTTP 409 with a "paused by health"
    detail message so the operator's UI can show a tooltip."""


class UnknownJob(TaskError):  # noqa: N818
    """Raised when a trigger / read by job_id targets a row that
    doesn't exist. Maps to HTTP 404."""


class ScheduleParseError(TaskError):
    """The ``schedule_cron`` expression failed APScheduler's
    cron parser, OR ``schedule_interval_seconds < 30``, OR both
    schedule fields were set / unset against the
    ``auto_check_added`` event-driven exception. Surfaced at
    save time as HTTP 400 (FR-025)."""


class ShutdownCancelled(TaskError):  # noqa: N818
    """Raised inside a runner's ``cancellation_event`` await when
    the lifespan handler signals shutdown. The runner catches it
    to record a ``cancelled`` job_run row, then re-raises so
    the scheduler service tears down cleanly (FR-021)."""


__all__ = [
    "JobAlreadyRunning",
    "JobDisabled",
    "ScheduleParseError",
    "ShutdownCancelled",
    "TaskError",
    "UnknownJob",
]
