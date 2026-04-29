# Implementation Plan: Tasks & Scheduler

**Branch**: `012-tasks-scheduler` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/012-tasks-scheduler/spec.md`
**Depends on**: every prior spec (this is the orchestrator).

## Summary

The Tasks & Scheduler subsystem is the orchestrator: it fires the
runners that earlier specs already exposed (`run_missing_search`,
`HealthEngine.refresh()`, `IndexerRssSync.sync_all_enabled_indexers()`,
`scan_full`, etc.) on documented cadences, plus it provides the
manual-trigger surface, the Sonarr-compat `/command` endpoint, the
WebSocket progress events, and the lifecycle policies (auto-pause on
critical health, graceful shutdown).

Three deliverables on top of the existing scaffolding:

1. **A scheduler service** built on APScheduler with `AsyncIOExecutor`
   and `SQLAlchemyJobStore`. No Celery, no Redis broker, no separate
   worker — everything runs in the FastAPI event loop.
2. **A `JobRunner` Protocol** that earlier modules implement; the
   scheduler is oblivious to what each runner does.
3. **A small set of new runners** that earlier specs deferred to this
   one: `BackupRunner` (DB + config snapshot to disk),
   `RefreshAllMetadataRunner` (paginated bulk variant of spec 002's
   per-Game refresh), `DatUpdateRunner` (downloads fresh DATs from
   No-Intro and friends; spec 001 only ingested locally-available
   ones).

Plus the management surface: CRUD on `/api/v3/system/tasks`, manual
triggers, cooperative cancellation, schedule mutation, and the
`POST /api/v3/command` Sonarr-compat alias.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: `apscheduler>=3.10`, SQLAlchemy 2.0 (async),
Pydantic v2, Alembic, structlog. **No new HTTP client.** The
WebSocket producer is in this feature; the consumer is in spec 014.
**Storage**: SQLite default / PostgreSQL 15+ optional. Two new tables
(`job`, `job_run`). APScheduler's `SQLAlchemyJobStore` lays down a
small `apscheduler_jobs` table on its own schema; the migration
either creates that table directly or accepts that APScheduler
creates it on first use (we do the former for predictability).
**Testing**: pytest, pytest-asyncio, pytest-cov, freezegun
(scheduler tick simulation, misfire grace, shutdown deadline),
TestClient (FastAPI), an in-memory APScheduler with a mock job
store fixture for unit tests.
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under
`src/romarr/tasks/`.
**Performance Goals**:
- Idle scheduler overhead < 1 % CPU on a typical home-server VM
  (SC-009).
- Schedule mutation latency < 60 s (SC-007 — scheduler tick budget).
- WebSocket throttling: ≤ 10 emissions/sec/runId (FR-023).
- Graceful shutdown deadline: 30 s + 5 s force-terminate window
  (FR-021).
**Constraints**:
- Single-instance design (Constitution Article I; no distributed
  scheduling).
- Auto-pause on critical health (FR-018).
- Misfire grace 60 min (FR-007).
- Concurrency cap honoured per job (FR-012).
- WS progress events MUST be lossy (no replay; clients fill gaps via
  REST polling).
**Scale/Scope**:
- Jobs per instance: 9 default + maybe 5–10 operator-added; tens
  total worst case.
- Job runs per day: hundreds (RSS sync + health checks dominate).
- `job_run` table grows linearly; cleanup is a future spec.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| I — Project Identity & Distribution | Single-instance design; no Celery, no separate worker; APScheduler in the FastAPI loop. | ✅ Conformant — assumption documented; multi-instance use is explicitly unsupported. |
| III — Technology Stack (Locked) | APScheduler is the documented "Scheduler" of Article III. SQLAlchemy 2.0 async + Pydantic v2 + Alembic; no new tech. | ✅ Conformant. |
| XVI — Quality Gates | ≥ 75% coverage on `tasks/` (SC-010); idle CPU < 1 % (SC-009); zero ruff warnings. | ✅ Conformant. |
| XVII — Idempotency & Safety | Concurrency cap (FR-012); misfire grace (FR-007); auto-pause on critical health (FR-018); graceful shutdown (FR-020-FR-021); seeder idempotent (FR-004 + edit-detection FR-008). | ✅ Conformant. |

**Result**: GREEN. No constitutional violations; **Complexity
Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/012-tasks-scheduler/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # job + job_run tables + value types
├── tasks.md             # 11-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── tasks/                               # NEW — top-level module
│   ├── __init__.py                       # public re-exports: SchedulerService, JobRunner, JobContext, JobResult
│   ├── types.py                          # JobContext, JobResult, JobStatus enum, JobSummary
│   ├── errors.py                         # JobAlreadyRunning, JobDisabled, UnknownJob, ScheduleParseError, ShutdownCancelled
│   ├── seeder.py                         # default-job catalogue + idempotent seeder
│   ├── scheduler.py                      # SchedulerService — APScheduler wrapper
│   ├── runner_protocol.py                # JobRunner Protocol + a Registry that maps job names to implementations
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── lifecycle.py                  # job_run row create/update; status transitions
│   │   ├── progress.py                   # WS broadcaster with throttling (≤ 10/s per runId)
│   │   ├── cancellation.py               # cancellation_event registry; force-terminate fallback
│   │   └── auto_pause.py                 # consult spec 011's HealthSnapshot before each scheduled tick
│   ├── runners/
│   │   ├── __init__.py
│   │   ├── adapters.py                   # thin adapters wrapping spec functions into the JobRunner Protocol
│   │   ├── backup.py                     # BackupRunner — DB snapshot + config TAR.gz to backup_path
│   │   ├── refresh_all_metadata.py       # RefreshAllMetadataRunner — paginated bulk variant of spec 002
│   │   ├── dat_update.py                 # DatUpdateRunner — download fresh DATs from documented sources
│   │   └── auto_check_added.py           # AutoCheckAddedRunner — wires spec 007's run_search_on_add to the OnGameAdded event
│   ├── command_aliases.py                # Sonarr-compat command-name → job-name mapping
│   ├── shutdown.py                       # SIGTERM handler; 30-s wait; cancellation_event setting; 5-s force-terminate
│   ├── models.py                         # Job + JobRun SQLAlchemy 2.0 models
│   ├── schemas.py                        # Pydantic *Read/*Create/*Update + TriggerResponse, CommandPayload, CommandStatus
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── tasks.py                      # /api/v3/system/tasks*
│       ├── runs.py                       # /api/v3/system/tasks/{name}/runs*
│       └── command.py                    # /api/v3/command + /api/v3/command/{id}
└── db/
    └── alembic/
        └── versions/
            └── 0012_tasks.py              # NEW migration: job + job_run + APScheduler's table

tests/
├── tasks/
│   ├── conftest.py                       # in-memory APScheduler fixture, mock JobRunners, mock health snapshot
│   ├── test_models.py
│   ├── test_migration_0012.py
│   ├── test_seeder.py                    # 9 defaults + idempotency + edit preservation
│   ├── test_scheduler.py                 # bootstrap registers enabled jobs only
│   ├── test_runner_protocol.py           # adapter wraps spec functions correctly
│   ├── execution/
│   │   ├── test_lifecycle.py             # job_run row created on start, updated on finish
│   │   ├── test_progress.py              # WS throttling (FR-023)
│   │   ├── test_cancellation.py          # cooperative + force-terminate (FR-021)
│   │   └── test_auto_pause.py            # SC-005: error-severity health → suppression
│   ├── runners/
│   │   ├── test_backup.py
│   │   ├── test_refresh_all_metadata.py
│   │   ├── test_dat_update.py
│   │   └── test_auto_check_added.py      # event-driven from OnGameAdded
│   ├── test_concurrent_triggers.py       # FR-012 + SC-003 (HTTP 409)
│   ├── test_misfire_grace.py             # SC-004 (8-hour catch-up)
│   ├── test_graceful_shutdown.py         # SC-006 (30-s + 5-s)
│   ├── test_command_aliases.py           # Sonarr-compat names map correctly
│   └── api/
│       ├── test_task_endpoints.py
│       ├── test_trigger_endpoint.py
│       ├── test_cancel_endpoint.py
│       ├── test_runs_endpoint.py
│       └── test_command_endpoint.py
```

**Structure Decision**: keep the **scheduler** as a singleton service
(`SchedulerService`) rather than scattered module-level functions —
this is the only place in the codebase that owns global mutable
state (APScheduler's job registry). The `JobRunner` Protocol lives
under `tasks/` rather than each module so the scheduler imports a
single Protocol and not 9 distinct module-specific shapes; the
adapters (`tasks/runners/adapters.py`) wrap each module's existing
function into the Protocol.

The **WS broadcaster** is in this feature (producer side); the
WebSocket connection handler at `/signalr/messages` is shipped by
spec 014 (REST API & WebSocket). The plan documents the contract
between them: the broadcaster publishes events on an in-process
channel, spec 014's handler consumes them.

## Phase 0 — Research

Three small research items resolved before code.

1. **APScheduler async integration** — `AsyncIOScheduler` runs in
   the FastAPI event loop; `start()` is non-blocking. Each runner is
   wrapped via `scheduler.add_job(coro_or_callable, ...)` where the
   callable is a small adapter that constructs `JobContext`, awaits
   the runner, and writes the `JobResult` to `job_run`.
2. **`SQLAlchemyJobStore` schema** — APScheduler creates an
   `apscheduler_jobs` table on first use; we let the Alembic
   migration declare it explicitly so the schema is reproducible
   (test snapshots match). The table has columns `id`, `next_run_time`,
   `job_state` (BLOB).
3. **WS progress throttling** — implemented as a per-runId asyncio
   throttler: keep last-emit timestamp; only forward an event when
   ≥ 100 ms has elapsed since the last one. The throttler may
   COALESCE intermediate progress (the latest `(current, total,
   message)` triple wins). Final `taskFinished` events are NEVER
   throttled — they always go through.

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for `job`, `job_run`, plus the explicit
  declaration of APScheduler's `apscheduler_jobs` table; the value
  types `JobContext`, `JobResult`, `JobSummary`,
  `CommandPayload`/`CommandStatus`.
- No `contracts/` — endpoint stubs only; full payload schemas come
  from the captured Sonarr command JSON shapes.
- No `quickstart.md` — the README's "Scheduling" section ships with
  the API spec.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **`BackupRunner` contract** (FR-027a) — single tarball per run at
  `<data>/backups/romarr-<UTC ISO 8601>.tar.gz`. Contents: DB snapshot
  (SQLite `VACUUM INTO` or `pg_dump --no-owner --format=custom`,
  autodetected by SQLAlchemy URL), `.env`, and
  `data/apprise-plugins/` only when both present AND
  `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS = true`. Excludes ROM files and
  `data/covers/`. Retention: keep most recent 14; older deleted in same
  run. Failures emit `OnHealthIssue` `category = 'backup'`. Off-machine
  replication is the operator's responsibility.
- **Per-job timezone for cron** (FR-007a) — new `job.schedule_timezone`
  column (NULL = UTC; otherwise IANA name). APScheduler evaluates cron
  in that timezone. All API timestamps returned in UTC ISO 8601 with
  `Z`. PATCH validation rejects invalid IANA names.
- **`job_run` per-job retention cap** (FR-002a) — bulk DELETE at the
  end of every successful run keeps the 1,000 most recent rows per
  `job_id` (ordered by `started_at` desc, skip 1000, delete rest).
  Total table size ~9,000 rows. Per-job (not global) prevents chatty
  jobs from starving quieter ones.
- **Single-instance enforcement via DB advisory lock** (FR-005a) —
  scheduler bootstrap acquires a fixed 64-bit lock key
  (`ROMARR_SCHEDULER_LOCK_KEY`). PostgreSQL: `pg_try_advisory_lock`.
  SQLite: a `scheduler_lock` table with one sentinel row, NULLable
  `holder_pid` + `acquired_at`, 30 s heartbeat TTL. Failure to acquire
  → scheduler component refuses to start; rest of the app keeps running;
  loud `OnHealthIssue` `category = 'scheduler-conflict'`. Auto-release
  on process death.
- **Admin-only mutations** (FR-027b) — POST `/trigger`, POST `/cancel`,
  PATCH `/tasks/{name}` require admin. `POST /api/v3/command` was
  already admin-only per spec 007. Reads accessible to any authenticated
  user.

### Migration delta

`0012_tasks.py`:
- `job.schedule_timezone TEXT NULL` (IANA name)
- `scheduler_lock` table (single row, holder_pid INT NULL,
  acquired_at TIMESTAMP NULL) — only created on SQLite; PostgreSQL
  uses `pg_try_advisory_lock` against an in-memory key
- `job_run` retention is enforced procedurally; no schema change

The 30-second heartbeat that refreshes `holder_pid` lives in the
scheduler's main loop on SQLite; on PostgreSQL the connection-bound
advisory lock auto-releases on connection close.
