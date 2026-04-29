# Feature Specification: Tasks & Scheduler

**Feature Branch**: `012-tasks-scheduler` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**: every prior spec — this feature is the orchestrator that fires
the runners those specs already exposed:
- `004-indexers` — `IndexerRssSync.sync_all_enabled_indexers()`
- `007-search-decision-engine` — `run_missing_search`, `run_cutoff_search`,
  `run_rss_sync`, `run_search_on_add`
- `002-metadata-aggregation` — `refresh_game_metadata` (per-Game) plus a
  paginated bulk variant introduced here
- `001-foundation` — DAT manager's `ingest(...)` plus a remote DAT downloader
  introduced here
- `009-library-exporters` — `scan_full`, `scan_incremental`
- `011-notifications-health` — `HealthEngine.refresh()`
- `010-auth-multiuser` — admin-only schedule mutations
- A new system-level `BackupRunner` introduced here (DB + config backup).
**Input**: User description: "APScheduler with AsyncIOExecutor running in the FastAPI event loop. Job state persisted to the main DB. Nine default jobs. Sonarr-compat command endpoint. WebSocket progress events. Auto-pause on critical health, graceful shutdown."

## Clarifications

### Session 2026-04-29

- Q: What is the scope, destination, and retention of the new `BackupRunner`? → A: Single tarball at `<data>/backups/romarr-<UTC-ISO-timestamp>.tar.gz` containing the DB snapshot (SQLite `VACUUM INTO` or `pg_dump --no-owner`, autodetect by connection URL) plus the encrypted-config files (`.env`, `data/apprise-plugins/` when present). Excludes ROM files and `data/covers/` (regenerable). Retention: keep the most recent 14 backups; older ones deleted in the same run
- Q: What timezone does the scheduler use to evaluate cron expressions? → A: Default UTC. Each `job` row carries an optional `schedule_timezone` column (IANA name like `Europe/Paris`) overriding UTC for that job only. All API timestamps (`next_run_at`, `last_run_at`, `started_at`, `finished_at`) are returned in UTC ISO 8601 with the `Z` suffix; the frontend converts for display. Operators who want a job at local 3am set the per-job timezone
- Q: What's the MVP retention policy for the `job_run` audit table? → A: Per-job retention of the **1,000 most recent rows** per `job_id`. At the end of every successful run, the runner executes a single bulk DELETE that removes rows beyond the per-job 1,000 cap. This bounds the table at ~9,000 rows on a default install regardless of cadence; per-job (not global) ensures chatty jobs (HealthCheck every 10 min) cannot starve quieter jobs of their audit history
- Q: How does the scheduler enforce the constitutional single-instance design when two Romarr processes share the same DB? → A: DB advisory lock at scheduler bootstrap. SQLite uses a sentinel-row LOCK; PostgreSQL uses `pg_try_advisory_lock`. The lock key is a fixed Romarr-specific 64-bit constant. If the lock is unavailable, the scheduler component refuses to start (loud structured error) but the rest of the application (REST API, WebSocket, non-scheduler work) keeps running so the second instance can still serve reads. The lock auto-releases on process death
- Q: What auth gates the tasks / command endpoints? → A: Admin-only on all mutating endpoints (`POST /system/tasks/{name}/trigger`, `POST /system/tasks/{name}/runs/{run_id}/cancel`, `PATCH /system/tasks/{name}`). `POST /api/v3/command` was already established admin-only by spec 007 FR-030a. Reads (`GET /system/tasks`, `GET /command/{id}`) accessible to any authenticated user. Same pattern as specs 003 / 004 / 005 / 006 / 007 / 008 / 009 / 011

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator gets a working scheduler on first boot (Priority: P1)

A Romarr operator launches the container for the first time. The
scheduler bootstraps, seeds the nine default jobs into the `job`
table, and starts firing them on their documented cadences. No
manual configuration needed — the operator immediately benefits
from automatic missing-search, RSS sync, health checks, etc.

**Why this priority**: Without this, the dozens of runner functions
shipped in earlier specs sit idle. The whole point of those specs
is the scheduler firing them.

**Independent Test**: Boot a fresh database; assert the `job` table
contains the nine documented rows with their default schedules;
assert APScheduler has registered them; freezegun-advance time and
verify each fires at its expected moment.

**Acceptance Scenarios**:

1. **Given** a fresh database, **When** the application starts,
   **Then** the `job` table is seeded with the nine documented
   default rows, the scheduler registers each enabled row with
   APScheduler, and `next_run_at` populates per the schedule.
2. **Given** the database already has the seeded rows, **When**
   the application restarts, **Then** the seeder MUST NOT
   duplicate them; counts are unchanged.
3. **Given** an operator-edited row (e.g., they disabled the
   `LibraryScan` job), **When** the application restarts, **Then**
   the operator's edit is preserved; the scheduler honours the
   `enabled = false` flag.

---

### User Story 2 — Manual trigger forces a job to run now (Priority: P1)

The operator just added a new indexer. They don't want to wait 12
hours for the next missing-search cycle; they hit the manual
trigger button and the search runs immediately. They get an
HTTP 202 with a `job_run_id` and watch progress in the UI's
Activity page.

**Why this priority**: Manual triggers are how operators iterate
during initial setup and during troubleshooting. Without them,
every config change requires a long wait.

**Independent Test**: POST `/api/v3/system/tasks/MissingSearch/trigger`;
assert HTTP 202 with `job_run_id`; verify the `job_run` row is
created with `status = 'running'`; on completion, the row carries
`status = 'success'` and the documented summary.

**Acceptance Scenarios**:

1. **Given** an enabled job, **When** the operator POSTs the
   trigger endpoint, **Then** the response is HTTP 202 with the
   new `job_run_id`; the underlying runner starts asynchronously.
2. **Given** a disabled job, **When** the operator POSTs without
   `?force=true`, **Then** the response is HTTP 409 with reason
   `job_disabled`; with `?force=true`, the job runs anyway and
   the response is HTTP 202.
3. **Given** a non-existent job name, **When** the operator
   POSTs, **Then** the response is HTTP 404.

---

### User Story 3 — Concurrent triggers are rejected (Priority: P1)

The operator clicks the "Search Missing" button twice in rapid
succession. The second click returns HTTP 409 with reason
`already_running` and does not start a second instance.

**Why this priority**: Without this, the operator hammering buttons
would launch parallel searches that fight each other (e.g., two
queue-refresh runs trying to update the same Release rows).

**Independent Test**: POST trigger; before the runner finishes,
POST again; assert the second call returns HTTP 409 with reason
`already_running`.

**Acceptance Scenarios**:

1. **Given** a job currently running with `max_concurrent_instances
   = 1` (default), **When** a second trigger arrives, **Then**
   the response is HTTP 409 with `reason = 'already_running'` and
   the active `job_run_id` of the in-flight run.
2. **Given** a job with `max_concurrent_instances = 2`, **When** a
   second trigger arrives during one in-flight run, **Then** it
   is accepted; a third triggers HTTP 409.
3. **Given** an in-flight run finishes, **When** a new trigger
   arrives, **Then** it is accepted as the next run.

---

### User Story 4 — Missed runs do not pile up (Priority: P2)

The operator powered off Romarr for 8 hours. On reboot, APScheduler
notices that two `MissingSearch` cycles, two `CutoffSearch` cycles,
and ~32 `HealthCheck` cycles were missed during the outage. With
the documented 60-minute misfire grace window, only the most recent
cycle fires once; the rest are skipped.

**Why this priority**: Without this, a week-long outage would
create a flood of catch-up runs that hammer external services.

**Independent Test**: Pre-populate the `job` table; freezegun-jump
time forward by 8 hours; bring the scheduler online; assert each
job runs at most once during the catch-up window.

**Acceptance Scenarios**:

1. **Given** a job whose last run is more than 60 minutes overdue,
   **When** the scheduler comes online, **Then** the misfire grace
   skips the missed run; the next firing happens at the next
   regular interval.
2. **Given** a job whose last run is within the 60-minute grace,
   **When** the scheduler comes online, **Then** it fires once
   and `next_run_at` advances to the next interval.

---

### User Story 5 — Critical health auto-pauses scheduled triggers (Priority: P2)

The DB connection has been failing for the last 30 seconds. The
last health check shows `db = error`. The scheduler suspends new
triggers (so a missing-search doesn't slam the broken DB) but
in-flight runs continue to completion. When health returns, the
scheduler resumes.

**Why this priority**: Without auto-pause, a sick instance would
keep firing scheduled work and worsen the failure mode.

**Independent Test**: Inject a `db = error` health row; trigger
the scheduler tick; assert no new jobs start; restore health;
assert scheduling resumes on the next tick.

**Acceptance Scenarios**:

1. **Given** the latest health snapshot reports any component as
   `error`, **When** a scheduled trigger fires (cron tick),
   **Then** the trigger is **suppressed**; an audit-log entry
   records the suppression reason.
2. **Given** a manual trigger arrives during the same suspension,
   **When** the operator passes `?force=true`, **Then** the
   trigger fires anyway (manual override beats auto-pause).
3. **Given** a job is **already running** when the health
   degrades, **When** auto-pause activates, **Then** the running
   job continues to completion; only **new** triggers are
   suppressed.

---

### User Story 6 — Graceful shutdown waits up to 30 seconds (Priority: P2)

The operator runs `docker stop romarr`. SIGTERM arrives. The
scheduler stops accepting new triggers and waits up to 30 seconds
for in-flight runs to finish. Runs that exceed the deadline are
cooperatively cancelled (their `cancellation_event` is set);
each cancelled run records `status = 'cancelled', error =
'shutdown'`.

**Why this priority**: Without graceful shutdown, mid-import
crashes leave half-written destination files; mid-RSS-sync
crashes leave stuck queue entries. Operationally critical.

**Independent Test**: Trigger a long-running job; signal SIGTERM
to the application; assert the scheduler waits for the runner to
finish if it does so within 30 s; otherwise the runner observes
`cancellation_event` set and returns with
`status = 'cancelled', error = 'shutdown'`.

**Acceptance Scenarios**:

1. **Given** an in-flight run finishes within 30 s of SIGTERM,
   **When** shutdown completes, **Then** the run's `job_run` row
   carries the natural success/failure status.
2. **Given** an in-flight run does not finish within 30 s, **When**
   the deadline elapses, **Then** the runner's
   `cancellation_event` is set; if the runner does not observe it
   within 5 additional seconds, the executor force-terminates the
   task. Either way, the row records
   `status = 'cancelled', error = 'shutdown'`.

---

### User Story 7 — Sonarr-compat /command endpoint accepts orchestration (Priority: P3)

The operator runs Notifiarr or another *arr-aware tool. It POSTs
`{"name": "MissingSearch"}` to `/api/v3/command`; Romarr maps the
command to the corresponding scheduled job's runner and returns a
command id. Subsequent GET `/api/v3/command/{id}` polls for status.

**Why this priority**: This is the constitutional Sonarr-compat
surface (Article IV). Useful but not blocking — the explicit
`/system/tasks/{name}/trigger` endpoint covers the Romarr-native
flow.

**Independent Test**: POST `{"name": "MissingSearch"}` to
`/api/v3/command`; assert HTTP 201 with a command id; GET
`/api/v3/command/{id}`; assert the response shape matches the
documented Sonarr v3 command JSON.

**Acceptance Scenarios**:

1. **Given** a Sonarr-compat command POST, **When** the name
   matches a known job (e.g., `MissingSearch`, `CutoffSearch`,
   `RssSync`, `Backup`, `RescanLibrary`), **Then** the command is
   accepted with HTTP 201 and a command id; the command id maps
   1:1 with a `job_run_id`.
2. **Given** a Sonarr-compat command with a payload (e.g.,
   `{"name": "RefreshGame", "gameId": 42}`), **When** the
   command runs, **Then** the runner receives the payload via
   `JobContext.kwargs` and processes only that target.
3. **Given** an unknown command name, **When** POSTed, **Then**
   the response is HTTP 400 with reason `unknown_command`.

---

### User Story 8 — WebSocket progress events drive the UI (Priority: P3)

The operator opens the Activity page in the browser. The page
subscribes to `/signalr/messages`. As scheduled jobs run, the
page shows live progress bars: "MissingSearch: 25 / 100,
Searching Sonic the Hedgehog…". When the job finishes, the bar
disappears and a summary toast pops up.

**Why this priority**: Critical to the UX but not blocking
day-1 — the UI can also poll `/api/v3/system/tasks` for status.

**Independent Test**: Connect a WebSocket client to
`/signalr/messages`; trigger a long-running job that calls
`progress_callback` 10 times; assert the client received one
`taskStarted`, ten `taskProgress`, and one `taskFinished` event
in order.

**Acceptance Scenarios**:

1. **Given** a connected WebSocket client, **When** a job starts,
   **Then** the client receives a `taskStarted` event with
   `{name, runId}`.
2. **Given** the same client, **When** the runner calls
   `progress_callback(current, total, message)`, **Then** the
   client receives a `taskProgress` event with the same triple.
3. **Given** the same client, **When** the runner finishes,
   **Then** the client receives a `taskFinished` event with
   `{runId, status, items_processed, summary}`.
4. **Given** a client that disconnects mid-run, **When** it
   reconnects, **Then** it receives only **future** events;
   missed events are NOT replayed (lossy WebSocket; clients
   poll `/api/v3/system/tasks` to fill gaps).

---

### Edge Cases

- A runner raises an unexpected exception → the job_run row
  records `status = 'failed'`, the structured error message goes
  to `last_error`, and the next scheduled run still happens (the
  failure does not poison the schedule).
- A runner returns `status = 'partial'` (e.g., RSS Sync skipped
  one rate-limited indexer) → the row records `partial` and the
  next run still happens; the UI shows a yellow indicator.
- A schedule modification with an invalid cron expression →
  PATCH returns HTTP 400 with the cron-parse error; nothing
  changes.
- The operator deletes a job row directly via DB → on next
  startup the seeder re-creates the missing default; the
  operator's other edits to other rows are preserved.
- Two different APScheduler instances accidentally point at the
  same DB (e.g., the operator runs two Romarr containers against
  the same SQLite file) → the DB advisory lock at bootstrap
  (FR-005a) prevents the second scheduler from starting; the
  loud structured `scheduler_lock_held_by_other_instance` error
  surfaces the misconfiguration as an `OnHealthIssue`. The
  second instance's REST API and WebSocket can still serve
  reads, but no scheduled work runs in it. Constitution
  Article I (single-instance design) is enforced, not just
  documented.
- A runner's `progress_callback` is called too frequently (e.g.,
  one per file across 100 000 files) → the WS broadcaster
  throttles emissions to 10/second per `runId` to avoid
  flooding the front-end.
- The cancellation_event is set but the runner ignores it for
  more than 5 seconds → the executor force-terminates the task
  and records `cancellation_forced = true` in the
  `output_summary`.
- A SQLAlchemyJobStore row gets corrupted (very rare) → on
  startup, APScheduler logs the error and skips the corrupt
  row; the seeder re-registers the corresponding default.
- The seeder runs against a partial existing state (e.g., 5 of
  9 default rows present) → only the missing 4 are inserted;
  the existing 5 are left alone.
- An auto-paused state lasts > 1 hour → after 1 hour, a single
  warning is logged so the operator knows scheduling is still
  paused (no event spam thereafter).

## Requirements *(mandatory)*

### Functional Requirements

**Persistence**

- **FR-001**: The system MUST persist a `job` table per
  `data-model.md` (one row per scheduled job, PK is the string
  `job_id` matching APScheduler).
- **FR-002**: The system MUST persist a `job_run` table per
  `data-model.md` (audit trail; one row per run, FK to `job`).
- **FR-002a**: The `job_run` table MUST be bounded by per-job
  retention of the **1,000 most recent rows per `job_id`**. At
  the end of every successful runner invocation, the scheduler
  MUST execute a single bulk DELETE removing rows beyond the
  cap for that job's id (ordered by `started_at` desc, skip the
  first 1,000, delete the rest). Pruning MUST happen in the
  same transaction that closes out the `job_run` row so
  failures during pruning don't leave orphaned audit data.
  This bounds the table at approximately 9,000 rows on a
  default install (9 jobs × 1,000) regardless of cron cadence;
  per-job (not global) retention prevents chatty jobs (e.g.,
  `HealthCheck` every 10 min) from starving quieter jobs'
  audit history.

**Default-job seeding**

- **FR-003**: On startup with an empty `job` table, the system
  MUST seed nine default jobs with the documented schedules:
  `RssSync` (15 min), `CutoffSearch` (6 h), `MissingSearch`
  (12 h), `RefreshGameMetadata` (24 h), `DatUpdate` (7 d),
  `Backup` (24 h), `HealthCheck` (10 min), `LibraryScan` (1 h,
  default disabled), `AutoCheckAdded` (event-driven, no
  schedule).
- **FR-004**: Re-running the seeder MUST be idempotent — operator-
  edited rows MUST be preserved (FR-008's edit-detection rule).

**Scheduler bootstrap**

- **FR-005**: On startup, the system MUST initialise APScheduler
  with `AsyncIOExecutor` and `SQLAlchemyJobStore` pointing at
  the main database (no Celery, no separate worker, no Redis
  broker).
- **FR-005a**: Before initialising APScheduler, the system MUST
  acquire a database advisory lock on a fixed Romarr-specific
  64-bit lock key (`ROMARR_SCHEDULER_LOCK_KEY`). For PostgreSQL
  this MUST use `pg_try_advisory_lock(<key>)`; for SQLite this
  MUST use an exclusive update on a single sentinel row in a
  `scheduler_lock` table (single row, NULLable `holder_pid` +
  `acquired_at`). When the lock cannot be acquired (another
  Romarr process is already holding it), the scheduler
  component MUST refuse to start, log a structured error
  identifying the conflict (`scheduler_lock_held_by_other_instance`),
  and emit an `OnHealthIssue` event with category
  `'scheduler-conflict'`. The rest of the application — REST
  API, WebSocket, non-scheduler request handling — MUST keep
  running so a second instance can still serve reads. The lock
  MUST auto-release on process death (PostgreSQL releases on
  connection close; the SQLite sentinel-row implementation
  uses a `holder_pid` heartbeat with a 30-second TTL so a
  crashed holder is reclaimable).
- **FR-006**: For every enabled `job` row, the scheduler MUST
  register the corresponding APScheduler job using its schedule
  (cron or interval). Disabled rows MUST NOT be registered.
- **FR-007**: APScheduler's `misfire_grace_time` MUST be 60
  minutes; runs missed by more than that MUST be skipped.
- **FR-007a**: The scheduler MUST evaluate cron expressions in
  **UTC by default**. Each `job` row MUST carry an optional
  `schedule_timezone` column (text, IANA timezone name such as
  `Europe/Paris`); when non-NULL, APScheduler MUST evaluate the
  cron in that timezone, otherwise UTC. Schedule mutations
  (FR-025) MAY set / clear / change the timezone alongside the
  cron expression. All `next_run_at`, `last_run_at`,
  `started_at`, and `finished_at` values returned through the
  API MUST be UTC ISO 8601 with the `Z` suffix; the frontend
  converts to the user's display timezone. Invalid timezone
  names MUST be rejected at PATCH validation with HTTP 400.

**Edit-detection rule**

- **FR-008**: The seeder MUST treat a row as "operator-edited"
  when `created_at != updated_at`. Edited rows MUST be left
  alone on subsequent seeder runs (no overwrite of operator
  preferences).

**JobRunner protocol**

- **FR-009**: Each module MUST expose its scheduled work via a
  `JobRunner` Protocol with one async method
  `run(ctx: JobContext) -> JobResult`. The scheduler MUST be
  oblivious to which module owns which runner.
- **FR-010**: `JobContext` MUST carry `job_id`, `started_at`,
  `progress_callback(current, total, message)`,
  `cancellation_event`, and (for parameterised jobs) a
  `kwargs` dict.
- **FR-011**: `JobResult` MUST carry `status` (`success` /
  `failed` / `partial` / `cancelled`), `items_processed`,
  `summary` (free-form dict), and an optional `error_message`.

**Concurrent execution**

- **FR-012**: The scheduler MUST honour `max_concurrent_instances`
  (default 1). A scheduled or manual trigger that would exceed
  the limit MUST be rejected with HTTP 409 and reason
  `already_running`.
- **FR-013**: Different jobs run independently; a slow runner of
  one job MUST NOT block another job's tick.

**Manual triggers**

- **FR-014**: The system MUST expose
  `POST /api/v3/system/tasks/{name}/trigger`; success returns
  HTTP 202 with `{job_run_id}`. The actual run is asynchronous.
- **FR-015**: A manual trigger on a disabled job MUST return
  HTTP 409 with reason `job_disabled` unless `?force=true` is
  supplied.

**Sonarr-compat command endpoint**

- **FR-016**: The system MUST expose `POST /api/v3/command`
  accepting Sonarr-shaped payloads
  `{"name": "<CommandName>", ...optionalKwargs}`. The handler
  MUST map the name to a scheduled job's runner and return
  HTTP 201 with the documented Sonarr command JSON. Recognised
  names are at minimum: `MissingSearch`, `CutoffSearch`,
  `RssSync`, `RefreshGame` (kwargs `gameId`),
  `RescanLibrary` (kwargs `libraryId`), `DownloadDats`,
  `IndexerSearch`, `Backup`.
- **FR-017**: `GET /api/v3/command/{id}` MUST return the
  Sonarr-shaped command status JSON, mirroring the underlying
  `job_run` row.

**Auto-pause on critical health**

- **FR-018**: When the latest health snapshot from spec 011
  carries any component at `error` severity, the scheduler MUST
  suppress new scheduled triggers for that tick. In-flight runs
  MUST continue to completion. Manual triggers with
  `?force=true` MUST still succeed.
- **FR-019**: Auto-pause status MUST be exposed via
  `GET /api/v3/system/tasks` (each row carries
  `is_paused_by_health: bool`).

**Graceful shutdown**

- **FR-020**: SIGTERM MUST stop the scheduler from accepting new
  triggers and wait up to 30 seconds for in-flight runs to
  finish.
- **FR-021**: After the 30-second deadline, in-flight runners'
  `cancellation_event` MUST be set; if a runner does not finish
  within 5 additional seconds, the executor force-terminates
  the task. Either way the `job_run` row records
  `status = 'cancelled', error = 'shutdown'`.

**WebSocket progress events**

- **FR-022**: The scheduler MUST emit `taskStarted` /
  `taskProgress` / `taskFinished` events to the
  `/signalr/messages` WebSocket channel introduced by spec 014
  (REST API & WebSocket). This feature ships only the producer
  side; the WebSocket handler is shipped in spec 014.
- **FR-023**: `progress_callback` invocations MUST be throttled
  to at most 10 emissions per second per `runId` to prevent UI
  flooding.

**Cancellation**

- **FR-024**: The system MUST expose
  `POST /api/v3/system/tasks/{name}/runs/{run_id}/cancel`
  which sets the run's `cancellation_event`; the runner is
  expected to observe it cooperatively. The endpoint returns
  HTTP 202 — cancellation is best-effort and not guaranteed to
  complete instantly.

**Schedule mutation**

- **FR-025**: `PATCH /api/v3/system/tasks/{name}` MUST accept
  partial updates to `schedule_cron`,
  `schedule_interval_seconds`, `enabled`,
  `max_concurrent_instances`, `max_retries`. Invalid cron
  expressions MUST be rejected at validation with HTTP 400 and
  the cron-parse error.
- **FR-026**: Schedule mutations MUST take effect immediately
  via APScheduler's `reschedule_job` — operators do NOT need
  to restart the application.

**Event-driven Auto Check Added**

- **FR-027**: The `AutoCheckAdded` runner MUST be wired to the
  Game-creation event (the API spec emits `OnGameAdded` whose
  handler triggers this runner via the same dispatch path as
  scheduled jobs). It MUST NOT have a cron schedule.

**Endpoint authorization**

- **FR-027b**: All mutating tasks/scheduler endpoints
  (`POST /api/v3/system/tasks/{name}/trigger`,
  `POST /api/v3/system/tasks/{name}/runs/{run_id}/cancel`,
  `PATCH /api/v3/system/tasks/{name}`) MUST require the caller
  to hold the `admin` role provided by the Auth spec.
  `POST /api/v3/command` was previously specified as admin-only
  by spec 007 FR-030a — that gate continues to apply unchanged.
  Read endpoints (`GET /api/v3/system/tasks`,
  `GET /api/v3/command/{id}`) MUST be accessible to any
  authenticated user. Same pattern as specs 003 / 004 / 005 /
  006 / 007 / 008 / 009 / 011.

**Backup runner**

- **FR-027a**: The `BackupRunner` (driving the default `Backup`
  job at 24 h cadence) MUST produce a single gzipped tarball at
  `<data>/backups/romarr-<UTC ISO 8601 timestamp>.tar.gz` per
  invocation. The tarball MUST contain:
  - The database snapshot — for SQLite via
    `VACUUM INTO '<tmp>/romarr.sqlite3'` (online-safe), for
    PostgreSQL via `pg_dump --no-owner --format=custom`. The
    backend is autodetected from the SQLAlchemy connection URL.
  - `.env` (the operator-supplied environment file) when present.
  - `data/apprise-plugins/` when the directory exists AND
    `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS = true` (per spec 011
    FR-001a).
  ROM files (`data/library/**`) and the cover cache
  (`data/covers/**`) MUST be excluded — they are regenerable
  and would dwarf the backup. Retention: at the end of every
  run, the runner MUST delete all but the **14 most recent**
  `romarr-*.tar.gz` files in `<data>/backups/`. Backup failures
  MUST emit `OnHealthIssue` via spec 011 with category
  `'backup'`. Off-machine replication is the operator's
  responsibility (their own rsync, restic, S3 sync, etc.,
  pointing at the backups directory).

### Key Entities

- **Job**: A configured scheduler entry with a schedule, an
  enabled flag, concurrency policy, and audit metadata. PK
  matches APScheduler's `job_id`.
- **Job Run**: An immutable audit row per execution attempt
  (success, partial, failure, or cancellation).
- **JobRunner**: A Protocol implemented by each module that
  exposes scheduled work. Pure dependency — the scheduler
  doesn't know what the runner does, only how to invoke it.
- **JobContext**: The parameters the scheduler hands to a runner
  (id, start time, progress callback, cancellation event,
  kwargs).
- **JobResult**: The structured outcome the runner returns
  (status, items_processed, summary, optional error).
- **Command**: The Sonarr-compat alias for a job run, exposed
  via `/api/v3/command`. A command id maps 1:1 to a
  `job_run_id`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a fresh boot, all nine documented default
  jobs exist in the `job` table with the right cadences and
  the operator-disabled `LibraryScan` defaults to `enabled =
  false` in 100% of test cases.
- **SC-002**: A manual trigger on an enabled job returns HTTP
  202 with a `job_run_id` and the runner runs to completion in
  100% of test cases (mocked runners).
- **SC-003**: A second trigger arriving while the first is
  still running returns HTTP 409 in 100% of test cases (with
  `max_concurrent_instances = 1`).
- **SC-004**: Missed runs older than 60 minutes are skipped in
  100% of catch-up scenarios (freezegun-validated across at
  least 8 hours of simulated downtime).
- **SC-005**: When the latest health snapshot has any
  `error`-severity component, scheduled triggers are
  suppressed; manual `?force=true` triggers still succeed in
  100% of test cases.
- **SC-006**: A SIGTERM-induced shutdown waits at most 30 s for
  in-flight runs and produces a `cancelled` row with
  `error = 'shutdown'` for any run that does not finish in time
  in 100% of test cases.
- **SC-007**: A schedule mutation via PATCH takes effect on the
  next scheduler tick (≤ 60 s) without an application restart
  in 100% of test cases.
- **SC-008**: WebSocket clients receive a `taskStarted` and a
  `taskFinished` event for every job run in 100% of test cases;
  `taskProgress` events are throttled to ≤ 10/s per runId.
- **SC-009**: Idle scheduler overhead (no jobs running) is < 1%
  CPU on a typical home-server VM (measured over a 5-minute
  idle window).
- **SC-010**: Test coverage on the tasks module MUST be at
  least 75%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Shutdown grace**: 30 seconds. After that, the executor sets
  `cancellation_event`; runners not honouring it within 5
  additional seconds are force-terminated. The `job_run` row
  records `cancelled` with `error = 'shutdown'`.
- **Auto-pause on critical health**: yes. The scheduler reads
  the health snapshot from spec 011; any `error`-severity
  component suspends scheduled triggers. Manual `?force=true`
  bypasses the pause.
- **Misfire grace**: 60 minutes. Missed runs older than that
  are skipped (no piling up).
- **RSS Sync rate-limits**: per-indexer rate limiting from spec
  004 applies. A rate-limited indexer is skipped for the
  current run with a structured warning; the next run retries.

Other assumptions:

- The scheduler is **single-instance** by design (Constitution
  Article I). Running two Romarr containers against the same
  SQLite file is explicitly unsupported; PostgreSQL deployments
  follow the same single-active-instance rule.
- The `job_run` table is bounded at MVP by per-job retention
  of the 1,000 most recent rows (FR-002a). The pruner runs at
  the end of every job invocation. Time-based pruning (e.g.,
  "older than 90 days") is not used at MVP; the row-count cap
  is simpler and more predictable.
- `progress_callback` throttling is handled inside the
  scheduler's broadcaster, not in the runners; runners may call
  it as often as they like and excess calls are coalesced.
- The Sonarr-compat command-name set ships with at least
  8 names (`MissingSearch`, `CutoffSearch`, `RssSync`,
  `RefreshGame`, `RescanLibrary`, `DownloadDats`,
  `IndexerSearch`, `Backup`); operators familiar with Sonarr
  will find their muscle memory works.

### Out of Scope

- UI for managing schedules (UI spec).
- Job priority queues (deferred — APScheduler doesn't have
  per-job priority natively).
- Distributed scheduling across multiple Romarr instances
  (firm out — single-instance design).
- Job dependencies / DAG (firm out — jobs are independent by
  contract).
- Cron-style triggers beyond standard 5-field cron (firm out).
- Job-run history pruning by absolute time / age (the MVP per-job
  row-count cap of 1,000 covers the operational concern; an
  additional time-based prune may be added in v1+ if needed).
- Retry-on-transient-error logic (the `max_retries` column
  exists for future use; current MVP does not auto-retry —
  failed runs require a manual trigger to retry).
