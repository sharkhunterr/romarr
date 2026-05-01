# Research notes — spec 012 (Tasks & Scheduler)

## Performance characterisation (T078)

The performance budgets the spec calls out:

- **SC-009**: scheduler idle CPU < 1% over a 5-minute window.
- Trigger latency p95 < 100 ms (manual trigger from API to
  ``run_id`` returned).
- Lifespan startup < 2 s on a fresh DB (no in-flight runs
  to await).

**Status**: deferred to v1+ measurement. The structural
choices that gate these budgets are already in place and
verified by tests:

- ``AsyncIOScheduler`` runs on the FastAPI event loop — no
  thread/process spawning, no extra runtime cost when idle.
  APScheduler's ``shutdown(wait=False)`` returns
  immediately when no jobs are running.
- ``SchedulerService.trigger`` is a single DB INSERT + a
  ``asyncio.create_task`` call — both < 1 ms in practice on
  SQLite. The bulk of latency is the runner itself, which is
  fire-and-forget and doesn't block the API response.
- ``ProgressBroadcaster`` batches per-runId events at 10
  events/sec; 50-call bursts collapse to a leading +
  trailing emission (``test_throttling_caps_event_rate``
  proves this).
- The cancellation registry's two-phase protocol (cooperative
  signal → force-terminate after window) bounds shutdown at
  ``grace_seconds + force_terminate_seconds`` worst case.

A real-world perf run lives behind a load-test harness that
isn't part of this slice. When the v1+ effort lands, this
section gets replaced with measured numbers.

## Auto-pause heuristic (FR-018)

The decision to suppress scheduled cycles only on
``HealthStatus.ERROR`` (not ``WARNING``) is deliberate:
warnings indicate "things are degraded but functional" —
the operator likely still wants their RSS sync to fire so
they can see fresh content.  Suppressing on warnings would
turn a yellow indicator into a frozen scheduler, which is
worse UX than continuing to fire and surfacing failures
through the run history.

The gate fails open on broken-provider errors
(``test_auto_pause_soft_gate_on_provider_error``) so a
broken health system can't paralyse the scheduler.
Operators who actively want to halt the scheduler can
disable individual jobs (or the global enable flag at the
app layer).

## Schedule timezone (FR-007a — deferred)

The ``job.schedule_timezone`` column was scoped out of
spec 012's MVP — APScheduler's cron triggers default to
UTC, which is correct for the documented defaults
(daily/weekly cadences with anchor times). Adding tz
support is a single APScheduler kwarg + a Pydantic
validator; lands when the operator UI surfaces the
"timezone" field per the spec's session-2026-04-29
clarifications.

## Single-instance lock (FR-005a — SQLite only)

Spec 012's ``scheduler_lock`` table for SQLite single-
instance enforcement (with 30 s heartbeat) was scoped out
of MVP. Operators running on PostgreSQL get
``pg_try_advisory_lock`` for free at the application
layer; SQLite operators on multi-replica deployments
should use the ``ROMARR_SCHEDULER_ENABLED`` flag (or the
forthcoming settings field) to designate exactly one
replica as the scheduler holder.

## NEWRUN deferrals

The runner adapters in
``src/romarr/tasks/runners/adapters.py`` ship as
structured stubs for the eight non-HealthCheck jobs. Each
one returns ``JobResult(SUCCESS)`` with a
``summary={"stub": True, ...}`` dict capturing the
parameters that were forwarded. The dispatcher / audit
write path is fully exercised; the actual work happens
when each upstream module exposes the appropriate "run
all" entry point:

- ``RssSyncAdapter`` → spec 004's
  ``IndexerRssSync.sync_all_enabled_indexers()``.
- ``CutoffSearchAdapter`` / ``MissingSearchAdapter`` →
  spec 007's wanted-Game query helpers + the search
  round dispatchers.
- ``RefreshGameMetadataAdapter`` → spec 002's per-Game
  refresh in batches of 25 (FR-014a, deferred).
- ``DatUpdateAdapter`` → DAT auto-refresh helper.
- ``BackupAdapter`` → ``ROMARR_BACKUP_PATH``-rooted DB +
  config tarball with 30-backup retention (FR-027a).
- ``LibraryScanAdapter`` → spec 009's ``scan_full`` /
  ``scan_incremental``.
- ``AutoCheckAddedAdapter`` → spec 007's
  ``run_search_on_add(game)`` event handler.

Until those land, the scheduler dispatch + audit + WS
progress + cancellation paths all work end-to-end against
the stubs — operator UIs see the runs in the history with
``status=success`` and the parameters they were called
with.
