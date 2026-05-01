---

description: "Granular task list for tasks & scheduler — APScheduler bootstrap, JobRunner protocol, lifecycle, auto-pause, graceful shutdown"
---

# Tasks: Tasks & Scheduler

**Input**: Design documents from `specs/012-tasks-scheduler/`
**Prerequisites**: every prior spec shipped — this is the orchestrator that
fires their runners.
**Tests**: MANDATORY (Constitution Article XVI; SC-010: ≥ 75% on tasks/)

**Organization**: 11 phases. Scaffolding → persistence → seeder → scheduler
service → runner protocol + adapters → execution helpers → new runners →
shutdown → command alias → API → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `SEED`, `SCHED`, `RUNNER`,
  `EXEC`, `NEWRUN`, `SHUTDOWN`, `CMD`, `API`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

- [X] T001 [SCAF] Update `pyproject.toml` — apscheduler dep
      already present (>=3.10 → 3.11.2 installed).
- [X] T002 [P] [SCAF] Create `src/romarr/tasks/__init__.py`
      exposing `JobContext`, `JobResult`, `JobStatus`,
      `TriggerKind`, `CommandPayload`, `CommandStatus` plus the
      five domain errors. `SchedulerService` + `JobRunner` are
      stubs added in subsequent slices.
- [X] T003 [P] [SCAF] Create `src/romarr/tasks/errors.py` —
      `TaskError` base + `JobAlreadyRunning` (HTTP 409),
      `JobDisabled` (HTTP 409 with paused-by-health detail),
      `UnknownJob` (HTTP 404), `ScheduleParseError` (HTTP 400),
      `ShutdownCancelled` (raised from runner cancellation).
- [X] T004 [P] [SCAF] Create `src/romarr/tasks/types.py` — every
      Pydantic / StrEnum from `data-model.md`'s "Value Types"
      section. `JobContext.parameters` (renamed from `kwargs`
      to avoid mypy `**kwargs`-style name collision) carries
      operator-supplied parameters for parameterised jobs.
- [X] T005 [SCAF] `tests/conftest.py` registers
      `romarr.tasks.models` so the in-memory schema includes
      `job` + `job_run` + `apscheduler_jobs`. The
      `in_memory_scheduler` APScheduler fixture lands with the
      SCHED slice (no scheduler service ships in SCAF/PERS).

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

### Tests (write first; must fail)

- [X] T006 [P] [PERS] `tests/tasks/test_models.py::test_job_round_trip`
      + `test_invalid_type_rejected_by_check` +
      `test_invalid_last_run_status_rejected` — round-trip a
      `Job` row; verify CHECK constraints on `type` and
      `last_run_status`.
- [X] T007 [P] [PERS] `tests/tasks/test_models.py::test_update_*`
      — Pydantic-level: cron and interval mutually exclusive
      (the auto_check_added event-driven exception is enforced
      at the read-side validator that the SEED slice will add);
      interval >= 30 s. Five test cases covering both-set,
      only-cron, only-interval, neither-set, sub-30-second
      values.
- [X] T008 [P] [PERS] `tests/tasks/test_models.py::test_job_run_round_trip`
      + `test_job_run_invalid_status_rejected` +
      `test_job_run_invalid_trigger_rejected` +
      `test_job_run_cascade_on_job_delete` — round-trip a
      `JobRun` row; CASCADE on job delete confirmed; user FK
      SET NULL exercised in the SCHED slice's lifecycle tests.
- [X] T009 [P] [PERS] `tests/tasks/test_migration_0012.py::test_migration_creates_three_tables`
      + `test_migration_is_reversible` +
      `test_migration_creates_documented_columns` — applying
      the migration creates `job`, `job_run`, AND
      `apscheduler_jobs`; downgrade rolls them back; column
      sets match the data-model.md DDL.

### Implementation

- [X] T010 [PERS] Create `src/romarr/tasks/models.py` — `Job`
      and `JobRun` SQLAlchemy 2.0 models. The `apscheduler_jobs`
      table is NOT mapped (APScheduler owns it at runtime);
      the migration creates it for reproducibility.
- [X] T011 [P] [PERS] Create `src/romarr/tasks/schemas.py` —
      `JobRead`, `JobUpdate` (with mutually-exclusive cron /
      interval validator + `interval >= 30` floor),
      `JobRunRead`, `TriggerRequest/Response`, plus re-exports
      of `CommandPayload` / `CommandStatus` from
      `romarr.tasks.types`.
- [X] T012 [PERS] Author
      `src/romarr/db/alembic/versions/0012_tasks.py` — DDL for
      `job` + `job_run` + `apscheduler_jobs`. `down_revision =
      "0011_notifications"`. Reversible (downgrade drops in
      dependency order).

**Checkpoint**: `alembic upgrade head` clean; PERS tests green.

---

## Phase 3: Seeder (`SEED`)

### Tests

- [X] T013 [P] [SEED] `tests/tasks/test_seeder.py::test_first_boot_seeds_nine`
      — fresh DB; runner invoked; assert exactly 9 rows with
      the documented `(type, schedule)` pairs and
      `is_factory_default = True` (SC-001). Plus
      `test_documented_schedules_match_catalogue` which pins
      every cell of the catalogue table to a specific schedule
      so a documented schedule change is caught here too.
- [X] T014 [P] [SEED] `tests/tasks/test_seeder.py::test_idempotent_rerun`
      — runner invoked a second time; row count unchanged.
      The seeder is "skip if id already exists" rather than
      "compare-and-write", so the second pass is a pure read.
- [X] T015 [P] [SEED] `tests/tasks/test_seeder.py::test_user_edit_is_preserved_across_rerun`
      — operator edits `MissingSearch.schedule_interval_seconds =
      7200` (and clears the cron); runner invoked again; the
      operator's value is preserved (FR-008).
- [X] T016 [P] [SEED] `tests/tasks/test_seeder.py::test_library_scan_default_disabled`
      + `test_other_defaults_are_enabled` — `LibraryScan.enabled
      = False` per the catalogue; the other eight defaults all
      ship enabled.

### Implementation

- [X] T017 [SEED] Create `src/romarr/tasks/seeder.py` —
      `seed_defaults(session)` with the catalogue from
      `data-model.md` as a frozen `tuple[_DefaultJob, ...]`.
      Returns the count of newly-inserted rows so callers can
      log "first boot detected, 9 jobs seeded" or "no-op,
      catalogue unchanged". The "skip if id exists" semantics
      preserve operator edits without needing the `(created_at
      != updated_at)` sentinel — once a row is in the table,
      the seeder never touches it again. A future-release
      catalogue addition is picked up automatically because the
      new id won't match any existing row. Plus a
      `test_partial_existing_inserts_only_missing` test
      simulating that upgrade scenario.

**Checkpoint**: SEED tests green.

---

## Phase 4: Scheduler Service (`SCHED`)

### Tests

- [X] T018 [P] [SCHED] `tests/tasks/test_scheduler.py::test_bootstrap_registers_enabled_only`
      — pre-populate `job` with 3 enabled + 1 disabled rows;
      `SchedulerService.start()`; assert APScheduler has the 3
      enabled jobs registered (FR-006). Plus
      `test_event_driven_job_skipped_in_bootstrap` covering
      `AutoCheckAdded`-style rows that have no schedule.
- [X] T019 [P] [SCHED] `tests/tasks/test_scheduler.py::test_misfire_grace_coalesces`
      — assert APScheduler job carries
      `misfire_grace_time=3600` + `coalesce=True` so an 8 h gap
      coalesces to one fire (SC-004). Wall-clock-based freezegun
      coverage of multiple-hour jumps lives in spec 013's
      end-to-end suite; the unit test pins the config.
- [X] T020 [P] [SCHED] `tests/tasks/test_scheduler.py::test_concurrent_trigger_raises_when_at_cap`
      — runner is in-flight; trigger again; raises
      `JobAlreadyRunning` (FR-012, SC-003). After the runner
      releases, a fresh trigger succeeds.
- [X] T021 [P] [SCHED] `tests/tasks/test_scheduler.py::test_max_concurrent_2`
      — `max_concurrent_instances = 2`; first two triggers
      succeed; third raises. After one slot frees up, the next
      trigger lands.
- [X] T022 [P] [SCHED] `tests/tasks/test_scheduler.py::test_reschedule_takes_effect`
      — PATCH-style schedule mutation: interval → interval, then
      interval → cron; assert the persisted Job row reflects
      both (FR-026, SC-007).

### Implementation

- [X] T023 [SCHED] Create `src/romarr/tasks/scheduler.py` —
      `SchedulerService` class wrapping `AsyncIOScheduler`.
      `start()` reads enabled `Job` rows and registers them
      with the right cron / interval trigger,
      `misfire_grace_time=3600`, `coalesce=True`,
      `max_instances=job.max_concurrent_instances`,
      `replace_existing=True`. `stop()` shuts down APScheduler
      and awaits inflight runner tasks. `trigger(job_id, *,
      triggered_by, triggered_by_user_id, parameters, force) ->
      int` writes a `job_run` row, dispatches the runner on the
      loop, registers the task in `_inflight[job_id]` so the
      next trigger sees the count for the cap check, and
      returns the new `run_id`. Concurrency check + insert +
      task registration happen under a single lock so two
      concurrent triggers can't both pass the cap. The
      lifecycle helper from the EXEC slice will own the
      `_finalise` write; for SCHED an inline minimum is
      sufficient.
- [X] T024 [SCHED] `SchedulerService.reschedule_job(name, *,
      cron, interval_seconds)` — mutually-exclusive validator
      ports the schema-layer rule into the runtime path; the
      method updates the `Job` row + APScheduler's trigger so
      the new cadence applies without restart.

**Deferred** to subsequent slices (each their own concern):

- Single-instance enforcement (FR-005a / `scheduler_lock`)
  for SQLite — needs a separate migration to add the table.
  Postgres uses `pg_try_advisory_lock` and is structurally
  fine on multi-replica.
- `job.schedule_timezone` (FR-007a) — APScheduler can take a
  tz on cron triggers; we plumb it when the column is added
  in a follow-up migration.
- Cancellation token plumbing through to the lifespan handler
  — lands in the SHUTDOWN slice (FR-021 graceful shutdown).
- Throttled progress callback — lands in the EXEC slice
  (FR-023, T033/T034).

**Checkpoint**: SCHED tests green.

---

## Phase 5: Runner Protocol & Adapters (`RUNNER`)

### Tests

- [ ] T025 [P] [RUNNER] `tests/tasks/test_runner_protocol.py::test_protocol_compliance`
      — parametrised over each adapter; assert each is a
      structural-typed `JobRunner` (`run` accepts `JobContext`,
      returns awaitable `JobResult`).
- [ ] T026 [P] [RUNNER] `tests/tasks/test_runner_protocol.py::test_adapters_pass_kwargs_through`
      — `RefreshGame` command with `kwargs = {"gameId": 42}`
      flows into the underlying spec function as `game_id=42`.
- [ ] T027 [P] [RUNNER] `tests/tasks/test_runner_protocol.py::test_progress_callback_throttled`
      — runner calls `progress_callback` 100 times in 100 ms;
      assert at most 10 events emitted on the WS channel
      (FR-023).

### Implementation

- [ ] T028 [RUNNER] Create `src/romarr/tasks/runner_protocol.py` —
      `JobRunner` Protocol + `RUNNER_REGISTRY` dict mapping job
      names to runner instances.
- [ ] T029 [RUNNER] Create `src/romarr/tasks/runners/adapters.py` —
      one adapter class per documented job, each wrapping the
      already-shipped function (e.g.,
      `RssSyncAdapter` wraps spec 004's `IndexerRssSync.sync_all_enabled_indexers()`,
      `MissingSearchAdapter` wraps spec 007's `run_missing_search()`,
      `HealthCheckAdapter` wraps spec 011's `HealthEngine.refresh()`,
      `LibraryScanAdapter` wraps spec 009's `scan_full()` and
      `scan_incremental()` per the schedule type).
- [ ] T030 [RUNNER] Wire the registry into `SchedulerService` so
      `trigger(name)` looks up the runner without conditional code.

**Checkpoint**: RUNNER tests green; every job has a registered
runner.

---

## Phase 6: Execution Helpers (`EXEC`)

### Tests

- [ ] T031 [P] [EXEC] `tests/tasks/execution/test_lifecycle.py::test_run_row_created_on_start`
      — call `lifecycle.start_run(...)`; assert a `JobRun` row
      appears with `status='running'`.
- [ ] T032 [P] [EXEC] `tests/tasks/execution/test_lifecycle.py::test_run_row_finalised_on_finish`
      — call `lifecycle.finish_run(...)`; row carries final status,
      `finished_at`, `duration_ms`.
- [ ] T033 [P] [EXEC] `tests/tasks/execution/test_progress.py::test_throttling_ten_per_second`
      — invoke `progress_callback` 50 times in 1 s; assert at most
      10 WS events emitted (FR-023, SC-008).
- [ ] T034 [P] [EXEC] `tests/tasks/execution/test_progress.py::test_final_event_never_throttled`
      — `taskFinished` always goes through even if it lands within
      the 100-ms throttle window.
- [ ] T035 [P] [EXEC] `tests/tasks/execution/test_cancellation.py::test_cooperative_cancel`
      — set `cancellation_event`; runner observes it within its
      loop and returns `status='cancelled'` (US for the cancel
      endpoint).
- [ ] T036 [P] [EXEC] `tests/tasks/execution/test_cancellation.py::test_force_terminate_after_5s`
      — runner ignores `cancellation_event`; after 5 s the executor
      force-terminates and writes
      `cancellation_forced = true` (FR-021).
- [ ] T037 [P] [EXEC] `tests/tasks/execution/test_auto_pause.py::test_error_severity_suppresses`
      — health snapshot has `error`; scheduled tick suppressed;
      audit log records the suppression (FR-018, SC-005).
- [ ] T038 [P] [EXEC] `tests/tasks/execution/test_auto_pause.py::test_force_overrides_pause`
      — manual trigger with `?force=true` succeeds even during
      auto-pause (FR-018 + US5.2).
- [ ] T039 [P] [EXEC] `tests/tasks/execution/test_auto_pause.py::test_inflight_runs_continue`
      — health degrades while a job is running; the running job
      finishes; only new triggers are suppressed (US5.3).

### Implementation

- [ ] T040 [EXEC] Create `src/romarr/tasks/execution/lifecycle.py`
      — async `start_run(...)`, `finish_run(...)`, `fail_run(...)`,
      `cancel_run(...)` helpers writing to `JobRun`.
- [ ] T041 [P] [EXEC] Create `src/romarr/tasks/execution/progress.py`
      — `WebSocketBroadcaster` with per-runId throttling (≤ 10/s
      per runId; 100-ms quiet window). Final `taskFinished` events
      bypass throttle.
- [ ] T042 [P] [EXEC] Create
      `src/romarr/tasks/execution/cancellation.py` — registry of
      live `cancellation_event` per `job_run_id`; force-terminate
      timeout helper.
- [ ] T043 [EXEC] Create `src/romarr/tasks/execution/auto_pause.py`
      — `is_paused() -> bool` consults spec 011's `HealthEngine`
      snapshot; integrated into `SchedulerService.trigger`.

**Checkpoint**: EXEC tests green.

---

## Phase 7: New Runners (`NEWRUN`)

**Purpose**: ship the three runners that earlier specs deferred to
this one.

### Tests

- [ ] T044 [P] [NEWRUN] `tests/tasks/runners/test_backup.py::test_writes_db_and_config_tar`
      — runner produces a `.tar.gz` at the configured backup_path;
      verifies the archive contains the SQLite file and a
      sanitized `config.json`.
- [ ] T045 [P] [NEWRUN] `tests/tasks/runners/test_backup.py::test_keeps_last_30`
      — runner keeps the most recent 30 backups; older ones pruned.
- [ ] T046 [P] [NEWRUN] `tests/tasks/runners/test_refresh_all_metadata.py::test_paginated`
      — 200 Games; runner processes them in batches of 25 to
      respect provider rate limits; respx asserts at most one
      provider call per Game.
- [ ] T047 [P] [NEWRUN] `tests/tasks/runners/test_dat_update.py::test_downloads_and_ingests`
      — respx-mocked No-Intro endpoint returns a sample DAT;
      runner downloads it, hands it to spec 001's `DatManager.ingest`,
      and emits `OnDatUpdate`.
- [ ] T048 [P] [NEWRUN] `tests/tasks/runners/test_auto_check_added.py::test_event_driven`
      — emit `OnGameAdded` event; runner is fired by the dispatcher
      (not by APScheduler's tick); calls spec 007's
      `run_search_on_add(game)`.

### Implementation

- [ ] T049 [NEWRUN] Create `src/romarr/tasks/runners/backup.py` —
      `BackupRunner` snapshots the DB (SQLite via `.backup` API or
      pg_dump for PostgreSQL) plus a sanitized config TAR.gz.
      Honours `ROMARR_BACKUP_PATH` and a 30-backup retention cap.
- [ ] T050 [P] [NEWRUN] Create
      `src/romarr/tasks/runners/refresh_all_metadata.py` —
      `RefreshAllMetadataRunner` paginates over Games and calls
      spec 002's per-Game refresh in batches.
- [ ] T051 [P] [NEWRUN] Create
      `src/romarr/tasks/runners/dat_update.py` — `DatUpdateRunner`
      downloads DATs from configured sources and calls spec 001's
      `DatManager.ingest`.
- [ ] T052 [P] [NEWRUN] Create
      `src/romarr/tasks/runners/auto_check_added.py` —
      `AutoCheckAddedRunner` subscribed to the `OnGameAdded` event
      channel from spec 011; fires spec 007's `run_search_on_add`.
      Registered with `RUNNER_REGISTRY` but NOT scheduled in
      APScheduler.

**Checkpoint**: NEWRUN tests green; the three new runners work
end-to-end.

---

## Phase 8: Graceful Shutdown (`SHUTDOWN`)

### Tests

- [ ] T053 [P] [SHUTDOWN] `tests/tasks/test_graceful_shutdown.py::test_finishes_within_30s`
      — runner finishes in 5 s; SIGTERM-equivalent invoked; shutdown
      completes; runner's row records natural status (US6.1).
- [ ] T054 [P] [SHUTDOWN] `tests/tasks/test_graceful_shutdown.py::test_cancellation_after_30s`
      — runner sleeps 60 s; shutdown invoked; after 30 s
      `cancellation_event` set; runner observes and returns
      `cancelled`; row records `error='shutdown'` (US6.2,
      SC-006).
- [ ] T055 [P] [SHUTDOWN] `tests/tasks/test_graceful_shutdown.py::test_force_terminate_after_5_more_seconds`
      — runner ignores `cancellation_event`; after 5 additional s
      the executor force-terminates; row records
      `cancellation_forced = true`.

### Implementation

- [ ] T056 [SHUTDOWN] Create `src/romarr/tasks/shutdown.py` —
      SIGTERM handler that:
      1. tells `SchedulerService` to stop accepting new triggers;
      2. awaits in-flight runs with a 30-s deadline;
      3. sets every remaining `cancellation_event`;
      4. waits up to 5 more seconds;
      5. force-terminates the asyncio tasks of any still-running
         runners and writes their `JobRun` rows.
- [ ] T057 [SHUTDOWN] Wire the SIGTERM handler into the FastAPI
      lifespan shutdown handler so it runs before the application
      tears down.

**Checkpoint**: SHUTDOWN tests green; SC-006 met.

---

## Phase 9: Sonarr-compat Command Endpoint (`CMD`)

### Tests

- [ ] T058 [P] [CMD] `tests/tasks/test_command_aliases.py::test_known_names_map`
      — table-driven over the 8+ documented Sonarr-compat names;
      each maps to the right job.
- [ ] T059 [P] [CMD] `tests/tasks/test_command_aliases.py::test_unknown_command_400`
      — POST `/api/v3/command` with `{"name": "Foo"}`; HTTP 400
      reason `unknown_command`.
- [ ] T060 [P] [CMD] `tests/tasks/api/test_command_endpoint.py::test_post_returns_command_id`
      — happy path; HTTP 201 with id; GET
      `/api/v3/command/{id}` returns `CommandStatus` JSON.
- [ ] T061 [P] [CMD] `tests/tasks/api/test_command_endpoint.py::test_kwargs_pass_through`
      — `{"name": "RefreshGame", "gameId": 42}`; the runner
      receives `kwargs = {"gameId": 42}`; the underlying spec 002
      function is called with `game_id=42`.

### Implementation

- [ ] T062 [CMD] Create `src/romarr/tasks/command_aliases.py` —
      pure mapping from Sonarr command names to job names + kwargs
      shape transformations (e.g., `gameId` → `game_id`).
- [ ] T063 [CMD] Create `src/romarr/tasks/api/command.py` — FastAPI
      router for `POST /api/v3/command` and `GET /api/v3/command/{id}`.
      The POST handler maps the command, calls
      `SchedulerService.trigger`, and returns a Sonarr-shaped
      `CommandStatus`.

**Checkpoint**: CMD tests green; Notifiarr-style integrations can
drive Romarr by command name.

---

## Phase 10: API (`API`)

### Tests

- [ ] T064 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_list_returns_status`
      — GET `/api/v3/system/tasks`; each row carries
      `next_run_at`, `last_run_at`, `is_paused_by_health`.
- [ ] T065 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_patch_invalid_cron_400`
      — PATCH with bad cron; HTTP 400 with parse error (FR-025).
- [ ] T066 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_patch_takes_effect_immediately`
      — PATCH `schedule_interval_seconds`; assert APScheduler's
      `next_run_at` updated within 60 s without restart (FR-026,
      SC-007).
- [ ] T067 [P] [API] `tests/tasks/api/test_trigger_endpoint.py::test_force_overrides_disabled`
      — disabled job; trigger with `?force=true`; HTTP 202.
- [ ] T068 [P] [API] `tests/tasks/api/test_cancel_endpoint.py::test_cancel_sets_event`
      — POST `/runs/{run_id}/cancel`; assert
      `cancellation_event.is_set()` for that run.
- [ ] T069 [P] [API] `tests/tasks/api/test_runs_endpoint.py::test_pagination_and_filter`
      — populate `JobRun` with mixed statuses; GET
      `/runs?status=failed&limit=10&offset=0` returns the right
      slice.
- [ ] T070 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_admin_only_mutations`
      — non-admin user attempts PATCH; HTTP 403; admin succeeds.

### Implementation

- [ ] T071 [API] Create `src/romarr/tasks/api/tasks.py` — FastAPI
      router for `GET / GET / PATCH` on `/api/v3/system/tasks*`.
      PATCH uses `require_role('admin')` from spec 010.
- [ ] T072 [P] [API] Add `POST /api/v3/system/tasks/{name}/trigger`
      to the same router.
- [ ] T073 [P] [API] Create `src/romarr/tasks/api/runs.py` — FastAPI
      router for `GET /api/v3/system/tasks/{name}/runs*` and
      `POST /api/v3/system/tasks/{name}/runs/{run_id}/cancel`.
- [ ] T074 [API] Wire all three routers into the application
      factory at their documented paths.

**Checkpoint**: API tests green; admin-only mutations enforced via
spec 010.

---

## Phase 11: Hardening (`HARD`)

- [ ] T075 [HARD] Run `pytest --cov=romarr.tasks` — verify ≥ 75%
      coverage (SC-010). Add targeted tests for any uncovered
      branch.
- [ ] T076 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/tasks/`.
- [ ] T077 [HARD] CI smoke test that asserts every entry in the
      seeder catalogue maps to a registered runner in
      `RUNNER_REGISTRY` — prevents an out-of-sync catalogue from
      shipping.
- [ ] T078 [HARD] Manual perf check — run the scheduler idle for
      5 minutes; record CPU usage in
      `specs/012-tasks-scheduler/research.md` (target < 1 % per
      SC-009).
- [ ] T079 [HARD] Update `pyproject.toml` `version = "0.12.0a1"`;
      add a one-line note to `CHANGELOG.md`: "0.12.0a1 — Tasks
      & Scheduler: APScheduler bootstrap, 9 default jobs,
      auto-pause on critical health, graceful shutdown."
- [ ] T080 [HARD] Final review: open
      `specs/012-tasks-scheduler/spec.md` and tick every Functional
      Requirement (FR-001 → FR-027) against a task ID; record gaps
      as follow-up items.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: prerequisite specs merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (SEED)**: depends on Phase 2.
- **Phase 4 (SCHED)**: depends on Phases 2, 3.
- **Phase 5 (RUNNER)**: depends on Phase 4 + every prior spec's
  exposed functions.
- **Phase 6 (EXEC)**: depends on Phase 4 + spec 011's
  `HealthEngine`.
- **Phase 7 (NEWRUN)**: depends on Phase 5 + the underlying spec
  functions for backup/metadata-refresh/dat-update.
- **Phase 8 (SHUTDOWN)**: depends on Phases 4, 6.
- **Phase 9 (CMD)**: depends on Phases 4, 5.
- **Phase 10 (API)**: depends on Phases 4, 6, 9.
- **Phase 11 (HARD)**: depends on Phase 10.

### Within-Phase Parallelism

- Phase 1: T002–T004 in parallel.
- Phase 2: T006–T009 in parallel; T010 + T011 in parallel.
- Phase 3: T013–T016 in parallel.
- Phase 4: T018–T022 in parallel; T023 + T024 sequential.
- Phase 5: T025–T027 in parallel; T028–T030 sequential.
- Phase 6: T031–T039 in parallel; T040–T043 in parallel.
- Phase 7: T044–T048 in parallel; T049–T052 in parallel.
- Phase 8: T053–T055 in parallel.
- Phase 9: T058–T061 in parallel.
- Phase 10: T064–T070 in parallel; T071–T073 in parallel.

### Critical Path

`SCAF → PERS → SEED → SCHED → RUNNER → API → HARD`. EXEC, NEWRUN,
SHUTDOWN, and CMD develop in parallel once SCHED is up.

### Implementation Strategy

- **Day 1**: Phase 1 (SCAF) + Phase 2 (PERS) + Phase 3 (SEED).
- **Day 2**: Phase 4 (SCHED) + Phase 5 (RUNNER).
- **Day 3**: Phase 6 (EXEC) + Phase 7 (NEWRUN) in parallel.
- **Day 4**: Phase 8 (SHUTDOWN) + Phase 9 (CMD).
- **Day 5**: Phase 10 (API).
- **Day 6**: Phase 11 (HARD).

This sizing assumes one developer working full-time. With two,
EXEC and NEWRUN split cleanly across them on Day 3.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the scheduler is delivered
  incrementally; each phase is independently shippable.
- Avoid: building a UI for schedule management (UI spec); building
  job priority queues (deferred); implementing distributed
  scheduling (firm out — single-instance design); auto-retry on
  failure (the `max_retries` column exists for future use; current
  MVP requires manual trigger to retry).
- Constitutional invariants under test:
  - **Article XVII (Idempotency & Safety)** — concurrent triggers
    rejected (T020); misfire grace skips overdue (T019);
    auto-pause on critical health (T037); graceful shutdown
    (T053-T055); idempotent seeder (T014).
  - **Article I (Single-instance)** — APScheduler runs in the
    FastAPI loop; no Celery / Redis broker / external workers.
  - **Article XVI (Quality Gates)** — ≥ 75 % coverage (T075);
    idle CPU < 1 % (T078, SC-009); throttled WS events (T033).
  - **Article III (Locked Stack)** — APScheduler is the documented
    Scheduler; no other scheduling library is added (T077 statically
    enforces the registry/seeder consistency).

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 [P] Implement `BackupRunner` in `src/romarr/tasks/runners/backup_runner.py` per FR-027a:
  - SQLite path: `VACUUM INTO '<tmp>/romarr.sqlite3'`
  - PostgreSQL path: `pg_dump --no-owner --format=custom`
  - Autodetect backend from SQLAlchemy connection URL
  - Build tarball at `<data>/backups/romarr-<UTC ISO 8601>.tar.gz`
  - Include: DB snapshot, `.env` (when present), `data/apprise-plugins/` (only when present AND `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS=true`)
  - Exclude: `data/library/**`, `data/covers/**`
  - Retention: keep most recent 14; delete older in same run
  - Failures emit `OnHealthIssue` with `category = 'backup'`
- [ ] CL002 Migration `0012_tasks.py` adds `job.schedule_timezone TEXT NULL` (NULL = UTC; otherwise IANA name) (FR-007a)
- [ ] CL003 [P] [US1] Update APScheduler bootstrap in `src/romarr/tasks/scheduler.py` to evaluate cron in `schedule_timezone` when set, otherwise UTC; ensure all API timestamps return as UTC ISO 8601 with `Z` suffix
- [ ] CL004 [P] PATCH `/api/v3/system/tasks/{name}` validator MUST reject invalid IANA timezone names with HTTP 400 in `src/romarr/tasks/api.py` (FR-007a)
- [ ] CL005 Migration `0012_tasks.py` (SQLite path only) creates `scheduler_lock` table with sentinel row `(id=1, holder_pid NULL, acquired_at NULL, heartbeat_at NULL)` (FR-005a)
- [ ] CL006 [US1] Implement DB advisory lock acquisition at scheduler bootstrap in `src/romarr/tasks/lock.py`:
  - PostgreSQL: `pg_try_advisory_lock(<ROMARR_SCHEDULER_LOCK_KEY>)`
  - SQLite: `UPDATE scheduler_lock SET holder_pid = ?, acquired_at = ?, heartbeat_at = ? WHERE id = 1 AND (holder_pid IS NULL OR heartbeat_at < datetime('now', '-30 seconds'))`
  - Failure → scheduler component refuses to start; rest of app keeps running; emit `OnHealthIssue` `category = 'scheduler-conflict'`
- [ ] CL007 [P] [US1] On SQLite, run a 30-second heartbeat loop from inside the scheduler that updates `scheduler_lock.heartbeat_at` to keep the lock alive; release on SIGTERM via the graceful-shutdown handler (FR-005a)
- [ ] CL008 [P] [US4] Implement `job_run` per-job retention pruner in `src/romarr/tasks/runner_dispatcher.py` — at end of every successful run, single bulk DELETE keeps the 1,000 most recent rows per `job_id` (FR-002a)
- [ ] CL009 [P] [Admin] Wire admin-role gate on `POST /api/v3/system/tasks/{name}/trigger`, `POST /api/v3/system/tasks/{name}/runs/{run_id}/cancel`, `PATCH /api/v3/system/tasks/{name}` in `src/romarr/tasks/api.py` (FR-027b)
- [ ] CL010 [P] Add tests in `tests/tasks/test_backup_runner.py` covering: SQLite path → tarball with VACUUM INTO snapshot; PostgreSQL path → tarball with pg_dump output; ROM files excluded; covers excluded; retention prunes to 14
- [ ] CL011 [P] Add tests in `tests/tasks/test_scheduler_lock.py` covering: first instance acquires; second instance refuses scheduler component but rest of app starts; first instance dies → second can acquire after 30 s heartbeat TTL
- [ ] CL012 [P] Add tests in `tests/tasks/test_timezone.py` covering: cron `0 3 * * *` with `schedule_timezone='Europe/Paris'` → fires at 02:00 UTC in winter, 01:00 UTC in summer; UTC default → fires at 03:00 UTC
- [ ] CL013 [P] Add tests in `tests/tasks/test_job_run_retention.py` covering: 1500 prior runs of one job → after next run, exactly 1000 most-recent kept; pruner doesn't affect other jobs' rows
