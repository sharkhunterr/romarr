"""Pydantic schemas for the tasks/scheduler API surface (spec 012).

Read / Update / Trigger / Run shapes plus the Sonarr-compat
command shapes (re-exported from :mod:`romarr.tasks.types`).
The two cross-field validators that matter at save time:

  * **Mutually-exclusive schedule** (FR-024): exactly one of
    ``schedule_cron`` / ``schedule_interval_seconds`` is set,
    EXCEPT for the event-driven ``auto_check_added`` job type.
  * **Interval floor** (FR-024): ``schedule_interval_seconds >= 30``
    so accidental tight loops can't slip past the API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from romarr.tasks.types import (
    CommandPayload,
    CommandStatus,
    JobStatus,
    TriggerKind,
)

# Re-export Sonarr-compat shapes so consumers can
# ``from romarr.tasks.schemas import CommandPayload``.
_ = (CommandPayload, CommandStatus)


_VALID_JOB_TYPES = (
    "rss_sync",
    "cutoff_search",
    "missing_search",
    "refresh_metadata",
    "dat_update",
    "backup",
    "health_check",
    "library_scan",
    "auto_check_added",
    "custom",
)


def _validate_schedule(
    *,
    job_type: str | None,
    cron: str | None,
    interval: int | None,
) -> None:
    """FR-024 / FR-025 cross-field check shared by Read / Update."""
    if job_type == "auto_check_added":
        # Event-driven: both must be NULL (no cron, no interval).
        if cron is not None or interval is not None:
            raise ValueError(
                "auto_check_added jobs are event-driven; "
                "schedule_cron and schedule_interval_seconds must both be NULL"
            )
        return
    if (cron is None) == (interval is None):
        raise ValueError(
            "exactly one of schedule_cron and "
            "schedule_interval_seconds must be set"
        )
    if interval is not None and interval < 30:
        raise ValueError(
            "schedule_interval_seconds must be >= 30 "
            "(no sub-30-second cadences)"
        )


class JobRead(BaseModel):
    """Read shape — every operator-visible column.

    ``is_paused_by_health`` is computed at API time (FR-019);
    ``current_run_id`` is populated when a run is in flight.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: Literal[
        "rss_sync",
        "cutoff_search",
        "missing_search",
        "refresh_metadata",
        "dat_update",
        "backup",
        "health_check",
        "library_scan",
        "auto_check_added",
        "custom",
    ]
    schedule_cron: str | None
    schedule_interval_seconds: int | None
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_run_duration_ms: int | None
    last_run_status: Literal[
        "success", "failed", "partial", "cancelled"
    ] | None
    last_error: str | None
    max_concurrent_instances: int
    max_retries: int
    is_factory_default: bool
    created_at: datetime
    updated_at: datetime

    # Computed at the API layer
    is_paused_by_health: bool = False
    current_run_id: int | None = None


class JobUpdate(BaseModel):
    """All fields optional + ``extra='forbid'`` so typos fail
    fast. Only mutable columns are exposed (no audit, no
    ``is_factory_default``)."""

    model_config = ConfigDict(extra="forbid")

    schedule_cron: str | None = None
    schedule_interval_seconds: Annotated[int | None, Field(ge=30)] = None
    enabled: bool | None = None
    max_concurrent_instances: Annotated[int | None, Field(ge=1)] = None
    max_retries: Annotated[int | None, Field(ge=0)] = None

    # type isn't on the update set — operators don't change a job's
    # runner kind through this API; that's a destroy + recreate flow.
    @model_validator(mode="after")
    def _exclusive_schedule(self) -> Self:
        cron = self.schedule_cron
        interval = self.schedule_interval_seconds
        if cron is not None and interval is not None:
            raise ValueError(
                "schedule_cron and schedule_interval_seconds "
                "are mutually exclusive"
            )
        return self


class JobRunRead(BaseModel):
    """Read-only history shape; the lifecycle helper writes
    these rows."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    status: JobStatus
    items_processed: int
    error_message: str | None
    output_summary: dict[str, Any] | None
    triggered_by: TriggerKind
    triggered_by_user_id: int | None
    cancellation_forced: bool


class TriggerRequest(BaseModel):
    """Body of ``POST /api/v3/job/{id}/trigger``.

    ``kwargs`` carries operator-supplied parameters for
    parameterised jobs (e.g. ``{"gameId": 42}`` for the
    ``RefreshGame`` runner).
    """

    model_config = ConfigDict(extra="forbid")

    kwargs: dict[str, Any] = Field(default_factory=dict)


class TriggerResponse(BaseModel):
    """Response body — points the operator at the freshly-
    written ``job_run`` row so they can poll for progress."""

    model_config = ConfigDict(frozen=True)

    job_run_id: int


__all__ = [
    "CommandPayload",
    "CommandStatus",
    "JobRead",
    "JobRunRead",
    "JobUpdate",
    "TriggerRequest",
    "TriggerResponse",
]
