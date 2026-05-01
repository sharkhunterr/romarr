"""Tasks & Scheduler subsystem (spec 012).

The scheduler is the project's central job orchestrator: it
runs every periodic job (RSS sync, cutoff search, missing
search, metadata refresh, DAT update, backup, health check,
library scan, auto-check-added) AND the on-demand commands
the API exposes (Sonarr-compat ``POST /api/v3/command``).

Public surface — populated incrementally as slices land:

* **SCAF + PERS** (this slice): module skeleton, value types,
  `Job` / `JobRun` SQLAlchemy models, Alembic migration `0012`.
  No scheduler yet; importing the module is a no-op.
* **SEED**: factory-default catalogue (9 jobs).
* **SCHED**: APScheduler bootstrap + `SchedulerService`.
* **RUNNER**: per-job runner protocol + adapters.
* **EXEC**: lifecycle / progress / cancellation / auto-pause
  helpers.
* **NEWRUN**: one new runner per default job.
* **SHUTDOWN**: lifespan integration.
* **CMD**: Sonarr-compat command alias.
* **API**: REST endpoints.
* **HARD**: coverage + version + FR sweep.
"""

from romarr.tasks.errors import (
    JobAlreadyRunning,
    JobDisabled,
    ScheduleParseError,
    ShutdownCancelled,
    TaskError,
    UnknownJob,
)
from romarr.tasks.types import (
    CommandPayload,
    CommandStatus,
    JobContext,
    JobResult,
    JobStatus,
    TriggerKind,
)

__all__ = [
    "CommandPayload",
    "CommandStatus",
    "JobAlreadyRunning",
    "JobContext",
    "JobDisabled",
    "JobResult",
    "JobStatus",
    "ScheduleParseError",
    "ShutdownCancelled",
    "TaskError",
    "TriggerKind",
    "UnknownJob",
]
