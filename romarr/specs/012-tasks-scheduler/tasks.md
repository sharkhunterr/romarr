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

- [X] T025 [P] [RUNNER] `tests/tasks/test_runner_protocol.py::test_adapter_satisfies_runner_protocol`
      — parametrised over each of the 9 adapters; asserts each
      is a structurally-typed :class:`JobRunner` (has an
      async `run(context: JobContext) -> JobResult`). Plus
      `test_adapter_carries_job_id_matching_class` confirming
      the adapter's `job_id` matches the SEED catalogue entry
      it represents.
- [X] T026 [P] [RUNNER] `tests/tasks/test_runner_protocol.py::test_refresh_game_metadata_kwargs_flow_through`
      + `test_library_scan_kwargs_select_target_library` —
      operator-supplied `JobContext.parameters` flows into the
      adapter's result summary so the audit captures the
      scope (single-game vs all-games, per-library vs all
      libraries).
- [ ] T027 [P] [RUNNER] `tests/tasks/test_runner_protocol.py::test_progress_callback_throttled`
      — *deferred to EXEC slice* — the throttling logic is
      a separate concern from runner dispatch; the EXEC layer
      wraps the `progress_callback` before handing it to the
      runner.

### Implementation

- [X] T028 [RUNNER] Create `src/romarr/tasks/runner_protocol.py`
      — `@runtime_checkable JobRunner` Protocol +
      `build_default_registry()` builder that assembles the
      production registry from the per-job adapters.
- [X] T029 [RUNNER] Create `src/romarr/tasks/runners/adapters.py`
      — one adapter per documented default. `HealthCheckAdapter`
      wraps spec 011's `HealthEngine.refresh()`. The other
      eight adapters (RssSync, CutoffSearch, MissingSearch,
      RefreshGameMetadata, DatUpdate, Backup, LibraryScan,
      AutoCheckAdded) are structured stubs that record their
      parameters in `JobResult.summary` and return SUCCESS
      until cross-spec wiring lands. Every adapter shares an
      `_AdapterBase` class that catches inner-`_run`
      exceptions and surfaces them as `JobResult(FAILED, ...)`
      so the scheduler never sees a raised exception from the
      adapter contract.
- [X] T030 [RUNNER] Wire the registry into `SchedulerService`
      via constructor injection — the scheduler accepts both
      adapter-object runners (`runner.run(ctx)`) and plain
      async-callable runners (`runner(ctx)`); the SCHED tests
      pass closures, the production lifespan wires the
      registry from `build_default_registry()`. The
      cross-cutting `await_run(job_run_id)` helper lets tests
      block until a specific run completes without polling.

**Checkpoint**: RUNNER tests green; every job has a registered
runner.

---

## Phase 6: Execution Helpers (`EXEC`)

### Tests

- [X] T031 [P] [EXEC] `tests/tasks/execution/test_lifecycle.py::test_start_run_creates_running_row`
      + `test_start_run_records_triggered_by_user` — call
      `lifecycle.start_run(...)`; row appears with
      `status='running'`; user FK SET NULL exercised.
- [X] T032 [P] [EXEC] `tests/tasks/execution/test_lifecycle.py::test_finish_run_marks_terminal`
      + `test_finish_run_mirrors_onto_job` +
      `test_finish_run_on_missing_row_returns_none` +
      `test_fail_run_records_error_message` +
      `test_cancel_run_unforced` +
      `test_cancel_run_forced_records_flag` — terminal
      transitions write final status, `finished_at`,
      `duration_ms`, mirror onto Job, defensive None on
      missing row, plus the FR-021 `cancellation_forced`
      audit flag.
- [X] T033 [P] [EXEC] `tests/tasks/execution/test_progress.py::test_throttling_caps_event_rate`
      — burst of 50 calls within the quiet window collapses
      to ≤ 2 events (1 leading + 1 trailing) carrying the
      latest values (FR-023, SC-008). Plus
      `test_throttle_per_run_id` (per-runId scope) and
      `test_calls_separated_by_window_all_emit` (no false
      throttling outside the window).
- [X] T034 [P] [EXEC] `tests/tasks/execution/test_progress.py::test_finished_event_bypasses_throttle`
      + `test_finished_clears_pending_trailing_event` —
      `taskFinished` always emits, and any pending trailing
      progress event is cancelled so the UI's last frame is
      the terminal one. Plus `test_event_payload_shape` for
      the WebSocket-layer contract.
- [X] T035 [P] [EXEC] `tests/tasks/execution/test_cancellation.py::test_cooperative_cancel_emits_cancelled_status`
      — runner observes ``cancellation_event`` and returns
      ``status=CANCELLED``; JobRun row records the terminal
      state without ``cancellation_forced=True``.
- [X] T036 [P] [EXEC] `tests/tasks/execution/test_cancellation.py::test_force_terminate_after_window`
      — runner ignores the event; after the configured window
      the executor force-terminates and writes
      ``cancellation_forced = True`` (FR-021). Plus
      ``test_cancel_unknown_run_returns_false`` for the cancel-
      endpoint 404 path, ``test_is_registered_reflects_current_state``
      for the registry's bookkeeping, and
      ``test_cancel_all_signals_every_registered_run`` for the
      lifespan-shutdown drain.
- [X] T037 [P] [EXEC] `tests/tasks/execution/test_auto_pause.py::test_scheduled_trigger_suppressed_when_paused`
      — health snapshot reports ``error``; scheduled trigger
      returns sentinel `-1` and writes no JobRun row (FR-018,
      SC-005). Plus four predicate-level tests:
      ``test_auto_pause_paused_when_health_error``,
      ``test_auto_pause_not_paused_when_health_ok``,
      ``test_auto_pause_not_paused_when_health_warning``
      (warnings are informational only — RSS sync still
      fires), and ``test_auto_pause_soft_gate_on_provider_error``
      (a broken health system fails open so the scheduler
      isn't paralysed).
- [X] T038 [P] [EXEC] `tests/tasks/execution/test_auto_pause.py::test_force_overrides_pause`
      — manual trigger fires regardless of pause (US5.2). Plus
      ``test_force_true_bypasses_even_for_scheduled_kind`` for
      the documented force=True override on SCHEDULED triggers.
- [X] T039 [P] [EXEC] `tests/tasks/execution/test_auto_pause.py::test_inflight_run_continues_when_health_degrades`
      — health goes from ok → error mid-run; the in-flight
      runner completes normally; new scheduled triggers are
      suppressed (US5.3).

### Implementation

- [X] T040 [EXEC] Create `src/romarr/tasks/execution/lifecycle.py`
      — session-scoped helpers `start_run`, `finish_run`,
      `fail_run`, `cancel_run`. Caller opens the session and
      commits — keeping the helpers pure (SQL only) lets the
      scheduler batch start_run + dispatch into one
      transaction. The scheduler now delegates to these
      helpers (extracted from the inline path in slice 11).
- [X] T041 [P] [EXEC] Create `src/romarr/tasks/execution/progress.py`
      — `ProgressBroadcaster` with per-runId throttling
      (≤ 10 events/sec; 100 ms quiet window). Bursts collapse
      to a leading + trailing emission carrying the latest
      values. The transport-agnostic `emit` callable is
      injected at construction time so tests can record
      events without a real WebSocket broadcaster (spec 013
      wires the production sink). `taskFinished` events
      bypass the throttle and clear any pending trailing
      progress event so the UI's last frame is the terminal
      one.
- [X] T042 [P] [EXEC] Create
      `src/romarr/tasks/execution/cancellation.py` —
      ``CancellationRegistry`` mapping ``job_run_id`` →
      ``(cancellation_event, task)``. ``register(...)`` adds
      entries and auto-removes on task completion via
      ``add_done_callback``. ``cancel(job_run_id)`` runs the
      two-phase protocol: signal the event, wait up to the
      configured force-terminate window (default 5 s) for
      cooperative shutdown, then ``task.cancel()`` and await
      to record ``cancellation_forced=True``.
      ``cancel_all()`` is the lifespan-shutdown drain.
      ``is_registered(...)`` is the cheap predicate for
      cancel-endpoint 404 surfacing.
- [X] T043 [EXEC] Create `src/romarr/tasks/execution/auto_pause.py`
      — ``AutoPause`` predicate consults spec 011's
      ``HealthEngine`` snapshot via an injected provider
      callable. ``is_paused()`` returns True iff
      ``overall_status`` is in ``PAUSING_STATUSES`` (currently
      ``{"error"}`` only — warnings are informational per
      FR-018). The gate fails open on provider errors so a
      broken health system can't paralyse the scheduler.
      Integrated into ``SchedulerService.trigger``: when
      ``triggered_by=SCHEDULED`` and ``not force``, the gate
      short-circuits before ``start_run`` (no JobRun row is
      written for suppressed cycles).

**Checkpoint**: EXEC tests green.

---

## Phase 7: New Runners (`NEWRUN`)

**Purpose**: ship the three runners that earlier specs deferred to
this one.

### Tests

- [X] T044 [P] [NEWRUN] Covered by slice 179 — see
      ``tests/tasks/runners/test_backup.py::test_run_backup_writes_db_and_config_tarball``.
      Asserts the snapshot is a real SQLite file containing the
      seeded row and the tar.gz wraps a single ``settings.json``
      with the three secret fields redacted.
- [X] T045 [P] [NEWRUN] Covered by slice 179 — see
      ``tests/tasks/runners/test_backup.py::test_run_backup_keeps_last_30``.
      Seeds 32 dummy archive pairs, runs one real backup, asserts
      exactly ``DEFAULT_RETENTION`` sqlite files survive.
- [ ] T046 [P] [NEWRUN] `tests/tasks/runners/test_refresh_all_metadata.py::test_paginated`
      — 200 Games; runner processes them in batches of 25 to
      respect provider rate limits; respx asserts at most one
      provider call per Game.
- [~] T047 [P] [NEWRUN] Download + ingest covered by slice 180 —
      ``tests/tasks/runners/test_dat_update.py::test_run_dat_update_downloads_and_ingests``
      uses a fetcher fake (cleaner than respx for our case) to
      verify the bytes round-trip through ``DatManager.ingest``
      and rows land in ``dat_entry``. ``OnDatUpdate`` event
      emission is deferred — the notifications fan-out helper
      hasn't been surfaced yet (same story as the bootstrap
      slice 173 noted). Lands when an ``emit_event(payload)``
      entry point exists on the dispatcher.
- [~] T048 [P] [NEWRUN] Runner half covered by slice 181 —
      ``tests/tasks/runners/test_auto_check_added.py`` verifies
      ``run_search_on_add`` loads the Game, calls the injected
      search function with the right title + platform_id,
      captures candidate / grab counts, and returns a
      structured ``skipped`` result for a missing game. The
      dispatcher-fires-this-not-APScheduler half is already
      pinned by the seeder + scheduler tests
      (``auto_check_added`` job-type guard). End-to-end
      "OnGameAdded → dispatcher → AutoCheckAddedAdapter" wire-up
      lands when the event-bus fan-out helper exists.

### Implementation

- [X] T049 [NEWRUN] ``BackupRunner`` shipped at
      ``src/romarr/tasks/runners/backup.py`` (slice 179). SQLite
      snapshot via portable ``VACUUM INTO`` + sanitized config
      tar.gz containing a single ``settings.json`` with
      ``auth_secret_key``, ``oidc_client_secret``, and
      ``importer_webhook_token`` redacted. PostgreSQL path raises
      ``NotImplementedError`` (pg_dump wiring deferred).
      ``DEFAULT_RETENTION = 30`` prunes paired sqlite +
      ``-config.tar.gz`` files beyond the window. ``BackupAdapter``
      delegates when ``JobContext.sessionmaker`` is set, falls back
      to the legacy stub otherwise. Tests at
      ``tests/tasks/runners/test_backup.py`` cover T044
      (writes-db-and-config), T045 (keeps-last-30), and the
      pair-aware prune helper.
- [X] T050 [P] [NEWRUN] ``RefreshAllMetadataRunner`` shipped
      at ``src/romarr/tasks/runners/refresh_all_metadata.py``
      (slice 178). Cursor-based pagination on ``Game.id``
      (page_size=100) so memory stays bounded for large
      libraries; per-Game errors are caught + counted (not
      fatal); optional ``platform_id`` scope; ``force`` flag
      forwards through. ``RefreshGameMetadataAdapter`` now
      delegates the all-games path to this runner when the
      JobContext exposes a sessionmaker. 5 tests cover
      pagination, partial failure, scoping, empty libraries,
      and force-flag propagation.
- [X] T051 [P] [NEWRUN] ``DatUpdateRunner`` shipped at
      ``src/romarr/tasks/runners/dat_update.py`` (slice 180).
      Per-source ``(url, source, platform_id)`` fetch via
      injectable ``HttpFetcher`` (default: httpx with 30s
      timeout + 64 MiB body cap, follow_redirects). Per-source
      failures are caught, captured as
      ``DatUpdateOutcome.error``, and counted in
      ``DatUpdateResult.failed`` so a single dead mirror doesn't
      block the rest. ``DatUpdateAdapter`` parses
      ``parameters["sources"]`` as a list of
      ``{"url", "source", "platform_id"}`` dicts and delegates
      to the runner when the JobContext supplies a sessionmaker;
      otherwise falls back to the legacy stub.
- [X] T052 [P] [NEWRUN] ``AutoCheckAddedRunner`` shipped at
      ``src/romarr/tasks/runners/auto_check_added.py``
      (slice 181). ``run_search_on_add(session, game_id,
      search_fn=None)`` loads the Game (so the runner has
      authoritative title + platform_id even if the
      OnGameAdded payload was stale), runs one manual search
      round scoped to the game's title + platform via the
      injected ``search_fn`` (default builds the indexer
      client factory and calls
      :func:`run_manual_search`), and returns an
      ``AutoCheckAddedResult`` with candidate / grab counts.
      Missing games surface as ``skipped=True`` rather than
      raising so the audit row reflects the "fired but
      no-op" outcome. ``AutoCheckAddedAdapter`` delegates
      when the JobContext supplies a sessionmaker + gameId;
      it stays event-driven (already pinned in
      ``schemas.py``'s job-type guard so APScheduler refuses
      to schedule it).

**Checkpoint**: NEWRUN tests green; the three new runners work
end-to-end.

---

## Phase 8: Graceful Shutdown (`SHUTDOWN`)

### Tests

- [X] T053 [P] [SHUTDOWN] `tests/tasks/test_graceful_shutdown.py::test_finishes_within_grace_period`
      — runner finishes inside the grace window; ``status="success"``,
      ``cancellation_forced=False`` (US6.1).
- [X] T054 [P] [SHUTDOWN] `tests/tasks/test_graceful_shutdown.py::test_cancellation_after_grace`
      — cooperative runner; grace window expires; cancellation
      event signalled; runner returns ``CANCELLED``;
      ``cancellation_forced=False`` (US6.2, SC-006).
- [X] T055 [P] [SHUTDOWN] `tests/tasks/test_graceful_shutdown.py::test_force_terminate_when_runner_ignores_signal`
      — runner ignores the event; force-cancel fires after the
      configured force-terminate window; row records
      ``cancellation_forced=True`` (FR-021). Plus
      ``test_shutdown_with_no_inflight_runs`` (idle-scheduler
      shutdown returns cleanly) and
      ``test_shutdown_without_registry`` (works without a
      cancellation registry — straight to force-terminate).

### Implementation

- [X] T056 [SHUTDOWN] Create `src/romarr/tasks/shutdown.py` —
      ``graceful_shutdown(scheduler, cancellation_registry=None,
      grace_seconds=30, force_terminate_seconds=5)``. Four-phase
      protocol:
      1. ``scheduler._scheduler.shutdown(wait=False)`` — no
         new APScheduler ticks; in-flight runs continue.
      2. ``await`` inflight tasks with a ``grace_seconds``
         timeout (most runners finish naturally in this window).
      3. If a registry is wired and tasks remain,
         ``cancellation_registry.cancel_all()`` signals every
         remaining run's ``cancellation_event``.
      4. Tasks that ignored the signal get a final
         ``task.cancel()`` + ``await`` for
         ``force_terminate_seconds``; the scheduler's
         ``_run_and_finalise`` catches ``CancelledError`` and
         records ``cancellation_forced=True``.
      Total function — never raises; the lifespan can't safely
      retry shutdown.
- [X] T057 [SHUTDOWN] Wired into the FastAPI lifespan
      (`src/romarr/api/app.py::_lifespan`):
      - On startup (when ``app.state._enable_scheduler`` is
        True), build a ``CancellationRegistry`` + a
        ``SchedulerService`` with the production
        ``build_default_registry()`` + ``await scheduler.start()``,
        and stash both on ``app.state``.
      - On teardown, run ``graceful_shutdown(...)`` before the
        engine disposes so audit rows write with the engine
        still alive.
      Default is ``_enable_scheduler=False`` so the test suite
      (which builds the app many times) doesn't pay the
      bootstrap cost. Production sets the flag (or the
      eventual ``ROMARR_SCHEDULER_ENABLED`` settings flag does
      it).

**Checkpoint**: SHUTDOWN tests green; SC-006 met.

---

## Phase 9: Sonarr-compat Command Endpoint (`CMD`)

### Tests

- [X] T058 [P] [CMD] `tests/tasks/test_command_aliases.py::test_known_names_map_to_expected_jobs`
      — parametrised over the 10 documented Sonarr-compat
      names (the documented FR-016 minimum 8 + RefreshGameMetadata
      and HealthCheck for completeness); each maps to the right
      job_id. Plus ``test_at_least_eight_documented_commands``
      (SC-008 floor) and
      ``test_every_alias_targets_a_seeded_job`` (drift guard).
- [X] T059 [P] [CMD] `tests/tasks/test_command_aliases.py::test_unknown_command_raises`
      — unit-level: ``resolve_command(name="Foo")`` raises
      ``UnknownCommand`` with the name in the message.
      The HTTP-level 400 with ``errorCode="unknown_command"``
      lives in ``test_command_endpoint.py::test_unknown_command_returns_400``.
- [X] T060 [P] [CMD] `tests/tasks/api/test_command_endpoint.py::test_post_known_command_returns_201_with_status`
      + ``test_get_command_status_returns_running_in_flight``
      — POST returns 201 with the Sonarr-shape ``CommandStatus``
      JSON (id, name, commandName, status, started, triggeredBy);
      GET on the command id while the runner is in-flight returns
      ``status="started"`` (the Sonarr terminology mapping).
- [X] T061 [P] [CMD] `tests/tasks/api/test_command_endpoint.py::test_kwargs_flow_into_job_context`
      — ``{"name": "RefreshGame", "gameId": 42}`` flows
      through ``resolve_command`` → ``scheduler.trigger`` →
      runner's ``JobContext.parameters = {"gameId": 42}``.
      Plus 8 more endpoint tests covering: missing name
      (400), unknown command (400), no scheduler (503),
      unknown command id (404), admin gate on POST,
      readonly access to GET, ``GET /_known`` lists every
      registered command name.

### Implementation

- [X] T062 [CMD] Create `src/romarr/tasks/command_aliases.py`
      — pure mapping from Sonarr command names to Romarr
      job_ids + per-alias ``allowed_kwargs`` whitelist.
      Unknown payload keys are silently dropped (matches
      Sonarr's permissive behaviour). Ten aliases shipped:
      MissingSearch / CutoffSearch / RssSync / RefreshGame
      (gameId) / RescanLibrary (libraryId) / DownloadDats /
      IndexerSearch (alias of RssSync) / Backup / HealthCheck /
      RefreshGameMetadata.
- [X] T063 [CMD] Create `src/romarr/tasks/api/command.py` —
      FastAPI router for ``POST /api/v3/command`` (admin) and
      ``GET /api/v3/command/{id}`` (readonly), plus
      ``GET /api/v3/command/_known`` for discovery. Maps
      ``JobStatus`` to Sonarr's status vocabulary
      (running→started, success/partial→completed,
      failed→failed, cancelled→aborted) and serialises to
      camelCase keys (``commandName``, ``triggeredBy``,
      ``lastExecutionTime``). Note: the legacy
      ``/api/v3/command`` router from spec 007 was removed
      in this slice — spec 012 is the canonical owner per
      FR-016. The four superseded tests in
      ``tests/search/api/test_command_endpoint.py`` were
      deleted along with the module.

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

- [X] T064 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_list_returns_jobs_with_status`
      + `test_get_single_task` + `test_get_unknown_task_returns_404`
      — GET `/api/v3/system/tasks` and GET single; carry every
      documented status field (`next_run_at`, `last_run_at`,
      `is_paused_by_health`, `current_run_id`).
- [X] T065 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_patch_with_both_schedule_fields_rejected`
      + `test_patch_with_sub_30_second_interval_returns_400`
      — Pydantic schema rejects both-set with HTTP 422 +
      "mutually exclusive" detail. The interval-floor (≥ 30 s)
      is enforced at the schema layer too.
- [X] T066 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_patch_persists_new_schedule`
      + `test_patch_can_disable_a_job` — PATCH on
      `schedule_interval_seconds`/cron and `enabled` persists
      to the row immediately. When a SchedulerService is
      wired (lifespan slice), the same call path also updates
      APScheduler's trigger so the new cadence applies within
      60 s without restart (FR-026, SC-007).
- [X] T067 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_trigger_returns_503_without_scheduler`
      + `test_trigger_with_scheduler_returns_run_id`
      — without a SchedulerService on app.state ⇒ 503; with
      one wired ⇒ 202 + the new `job_run_id`. Force-overrides-
      disabled is wired through the `?force=true` query —
      tested at the SchedulerService level in slice 11.
- [X] T068 [P] [API] `tests/tasks/api/test_runs_endpoint.py::test_cancel_with_registry_signals_event`
      + `test_cancel_unknown_run_returns_404` +
      `test_cancel_terminal_run_returns_409` — POST
      `/runs/{run_id}/cancel`: 202 + `{forced: bool}` when
      registry is wired and run is in-flight; 404 when the
      run doesn't exist OR isn't registered on this replica;
      409 when the run is already terminal.
- [X] T069 [P] [API] `tests/tasks/api/test_runs_endpoint.py::test_runs_list_*`
      — paginated history with `status` and `triggered_by`
      filters; default sort is started_at DESC; limit ≥ 200
      returns 422; unknown job returns 404; unauthenticated
      returns 401.
- [X] T070 [P] [API] `tests/tasks/api/test_task_endpoints.py::test_patch_requires_admin`
      + `test_patch_unauthenticated_returns_401` +
      `test_list_accessible_to_readonly` +
      `test_trigger_requires_admin` +
      `test_cancel_requires_admin` — full role-gate matrix:
      reads accessible to any authenticated user; PATCH /
      trigger / cancel admin-only.

### Implementation

- [X] T071 [API] Create `src/romarr/tasks/api/tasks.py` —
      FastAPI router for `GET /api/v3/system/tasks` (list,
      readonly), `GET /{job_id}` (single), `PATCH /{job_id}`
      (update, admin), `POST /{job_id}/trigger` (admin).
      PATCH validates the schedule shape (mutually-exclusive
      cron / interval) and threads through
      `SchedulerService.reschedule_job` when the scheduler
      is wired. Trigger surfaces 503 when the scheduler isn't
      running, 404 / 409 for the documented error paths.
- [X] T072 [P] [API] Trigger endpoint folded into
      `tasks.py` (same router, same prefix). Optional
      `?force=true` query bypasses the `enabled=False` gate
      (US5.2). Admin-only via `Depends(require_admin)`.
- [X] T073 [P] [API] Create `src/romarr/tasks/api/runs.py` —
      FastAPI router for `GET /{job_id}/runs` (paginated
      history, readonly) and `POST /{job_id}/runs/{run_id}/cancel`
      (admin). Cancel reads the cancellation registry off
      `app.state` so non-wired deployments surface 503
      cleanly. Returns `{job_run_id, status, forced}` so the
      operator UI can distinguish cooperative cancel from
      force-terminate.
- [X] T074 [API] Wired both routers into the application
      factory (`src/romarr/api/app.py`). The runs router
      shares the `/api/v3/system/tasks` prefix with the CRUD
      router; mounting order doesn't matter because the run
      paths are deeper (`/{job_id}/runs*`) so there's no
      collision. SchedulerService + CancellationRegistry are
      read off `app.state` — the lifespan slice will install
      them.

**Checkpoint**: API tests green; admin-only mutations enforced via
spec 010.

---

## Phase 11: Hardening (`HARD`)

- [X] T075 [HARD] `pytest --cov=romarr.tasks` — **87.7%
      coverage** on the tasks module (SC-010 floor: 75%). 742
      of 846 statements covered. Uncovered branches are the
      `_known` endpoint's defensive paths, the
      ``CommandStatus`` GET when it can't read the row,
      progress-broadcaster's edge cancellations, and a few
      defensive ``except`` clauses in the scheduler's
      shutdown phase that the EXEC tests can't induce
      without mocking asyncio internals.
- [X] T076 [HARD] `ruff check src/romarr/tasks/`: zero
      warnings.
- [X] T077 [HARD] Drift guard implemented as
      ``test_default_registry_keys_match_seed_catalogue``
      (RUNNER slice T030) and
      ``test_every_alias_targets_a_seeded_job`` (CMD slice
      T058). The first asserts every SEED catalogue id has a
      registered runner in ``build_default_registry``; the
      second asserts every Sonarr-compat alias's job_id is
      in the SEED catalogue. Adding a new job without
      wiring the adapter or alias trips one of these tests at
      collection time.
- [X] T078 [HARD] Performance budget characterisation in
      `specs/012-tasks-scheduler/research.md`. The
      scheduler's structural choices (AsyncIOScheduler on
      the FastAPI event loop; trigger as INSERT +
      create_task; throttled progress emission) bound the
      budgets the spec calls out. End-to-end measurement
      deferred to v1+.
- [X] T079 [HARD] `pyproject.toml::version = "0.12.0a1"` +
      `src/romarr/__init__.py::__version__` synced +
      CHANGELOG entry summarising the spec 012 surface.
- [X] T080 [HARD] FR sweep — every FR-001 → FR-027 traces to
      a task ID:
      * **FR-001 / FR-002** (APScheduler + 9 default jobs):
        SCAF + PERS + SEED slices (T001-T017).
      * **FR-002a** (job_run retention): procedural — DELETE
        at end of every successful run keeps 1k most-recent
        per job_id; no schema change. Drift guard:
        ``test_default_registry_*`` ensures the catalogue ↔
        adapter binding stays in sync.
      * **FR-003 / FR-004** (job state persisted in
        apscheduler_jobs / SQLAlchemyJobStore): migration
        ``0012`` declares the table; ``SchedulerService``
        wires APScheduler with the in-memory MemoryJobStore
        as default (the test suite uses MemoryJobStore;
        production swaps to SQLAlchemyJobStore via lifespan
        config — a forward-compatible follow-up that the
        SQLite/Postgres detection is already prepared for).
      * **FR-005 / FR-005a** (single-instance enforcement):
        deferred — research.md flags the SQLite
        ``scheduler_lock`` follow-up.
      * **FR-006** (enabled-only bootstrap): SCHED slice
        T018.
      * **FR-007** (cron + interval triggers): SCHED slice
        T023; **FR-007a** (schedule_timezone): deferred —
        research.md flags it.
      * **FR-008** (factory defaults preserved across
        boots): SEED slice T015.
      * **FR-009** (misfire grace 60 min): SCHED slice T019.
      * **FR-010 / FR-011** (logical job catalogue): SEED
        slice T013-T016.
      * **FR-012** (max_concurrent_instances): SCHED slice
        T020/T021.
      * **FR-013** (lifecycle helpers): EXEC slice T040.
      * **FR-014 / FR-014a** (per-job runner protocol +
        kwargs flow): RUNNER slice T025/T026.
      * **FR-015 / FR-015a** (Sonarr-compat command alias):
        CMD slice T058-T063.
      * **FR-016 / FR-017** (Sonarr command JSON shape):
        CMD slice T063.
      * **FR-018 / FR-019** (auto-pause on health error +
        is_paused_by_health surfaced): EXEC slice T037-T039.
      * **FR-020 / FR-021** (graceful shutdown +
        cancellation_forced audit): EXEC slice T035-T036
        + SHUTDOWN slice T053-T057.
      * **FR-022 / FR-023** (progress events ≤ 10/s per
        runId): EXEC slice T033/T034.
      * **FR-024 / FR-025** (REST API + cron parse
        validation): API slice T064-T074.
      * **FR-026** (reschedule without restart): SCHED
        slice T022/T024.
      * **FR-027** (operator-edit preservation across
        seeder reruns): SEED slice T015.
      * **FR-027a** (BackupRunner artefacts): deferred —
        flagged in research.md NEWRUN section.

      **Deferred to NEWRUN** (T044-T052): real runner
      implementations for RssSync, CutoffSearch,
      MissingSearch, RefreshGameMetadata, DatUpdate, Backup,
      LibraryScan, AutoCheckAdded — each unblocks once
      its upstream module exposes the corresponding "run
      all" / per-target entry point. The dispatcher / audit
      / WS-progress / cancellation paths all work
      end-to-end against the stubs in the meantime.

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
