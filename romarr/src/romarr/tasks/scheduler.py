"""SchedulerService — APScheduler bootstrap + trigger dispatch (T023/T024).

Wraps :class:`apscheduler.schedulers.asyncio.AsyncIOScheduler`
with the project's async-session lifecycle. Reads enabled
:class:`romarr.tasks.models.Job` rows on startup, registers each
with APScheduler under the right trigger, and exposes
``trigger(job_id, *, force=False, parameters=None) -> int`` so
the API + lifecycle helpers can fire a runner on demand.

Deferred to subsequent slices (each their own concern):

  * **Single-instance enforcement** (FR-005a / `scheduler_lock`):
    SQLite's advisory-lock equivalent + the 30 s heartbeat. The
    bootstrap path runs unconditionally for now — operators who
    need single-instance safety on SQLite get it once that
    slice lands.
  * **Schedule timezone** (FR-007a / `job.schedule_timezone`):
    APScheduler can take a tz on cron triggers; we plumb it
    when the column is added in a follow-up migration.
  * **Cancellation token plumbing**: the runner's
    ``JobContext.cancellation_event`` is constructed here but
    not yet wired to the lifespan handler — that lands in the
    SHUTDOWN slice.
  * **Progress throttling**: the
    ``JobContext.progress_callback`` is a no-op stub; the EXEC
    slice replaces it with the throttled WebSocket emitter.

What this module DOES handle:

  * Bootstrap of enabled jobs only (FR-006).
  * Cron and interval triggers (FR-024).
  * Misfire grace 60 min (FR-009 / SC-004) — APScheduler's
    ``coalesce=True`` + ``misfire_grace_time=3600`` means an
    8 h gap fires the most recent missed cycle once, not once
    per missed cycle.
  * Per-job concurrency cap (``max_concurrent_instances``) —
    raises :class:`JobAlreadyRunning` when the cap is hit
    (FR-012, SC-003).
  * Reschedule without restart (FR-026, SC-007).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-untyped]
from sqlalchemy import select

from romarr.tasks.errors import (
    JobAlreadyRunning,
    JobDisabled,
    ScheduleParseError,
    UnknownJob,
)
from romarr.tasks.execution.lifecycle import finish_run, start_run
from romarr.tasks.models import Job
from romarr.tasks.types import (
    JobContext,
    JobStatus,
    TriggerKind,
)

if TYPE_CHECKING:

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy.ext.asyncio.session import AsyncSession

    from romarr.tasks.execution.auto_pause import AutoPause
    from romarr.tasks.execution.cancellation import CancellationRegistry

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public type aliases


if TYPE_CHECKING:
    from romarr.tasks.runner_protocol import JobRunner as _JobRunner

type JobRunner = "_JobRunner"
"""Structural-typed runner protocol — see
:mod:`romarr.tasks.runner_protocol`. The dispatcher calls
``runner.run(context)`` and awaits the result."""


type JobRegistry = dict[str, JobRunner]
"""Job ids → runner. The ``SchedulerService`` looks up the
runner from this dict on every dispatch — empty registry means
"register the schedule but never fire", useful for tests that
exercise the trigger arithmetic without running real work."""


# ---------------------------------------------------------------------------
# SchedulerService


class SchedulerService:
    """One per-process orchestrator. Wraps APScheduler with the
    project's session factory + runner registry.

    The service does NOT own the session it commits with — the
    application factory passes a session_factory (the same one
    the API dependencies use) so lifespan cleanup is handled
    once.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        runners: JobRegistry,
        misfire_grace_seconds: int = 3600,
        auto_pause: AutoPause | None = None,
        cancellation_registry: CancellationRegistry | None = None,
        ws_bridge: Any = None,
        event_channel: Any = None,
    ) -> None:
        self._session_factory = session_factory
        self._runners = dict(runners)
        self._misfire_grace_seconds = misfire_grace_seconds
        self._auto_pause = auto_pause
        self._cancellation_registry = cancellation_registry
        # Optional WS bridge — when wired, every JobRun emits a
        # ``taskStarted`` / ``taskFinished`` envelope to live
        # operator sessions (spec 013 T064 / T068). Best-effort:
        # bridge errors are caught + logged so scheduler dispatch
        # never depends on WS delivery.
        self._ws_bridge = ws_bridge
        # Optional spec 011 EventChannel — passed into JobContext
        # so per-runner emitters (DatUpdate's ``OnDatUpdate``,
        # backup's outcome events, etc.) can publish through the
        # canonical fan-out point. Test contexts construct a
        # JobContext without it; runners short-circuit emission
        # when None.
        self._event_channel = event_channel
        self._scheduler = AsyncIOScheduler()
        self._inflight: dict[str, set[asyncio.Task[None]]] = {}
        self._inflight_lock = asyncio.Lock()
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle

    async def start(self) -> None:
        """Read enabled jobs and register each with APScheduler.

        Disabled jobs are skipped (FR-006). Jobs with neither
        cron nor interval (event-driven, e.g. ``AutoCheckAdded``)
        are also skipped — they're triggered by other code paths,
        not the scheduler.
        """
        if self._started:
            return
        async with self._session_factory() as session:
            jobs = (
                await session.execute(
                    select(Job).where(Job.enabled.is_(True))
                )
            ).scalars().all()

        for job in jobs:
            trigger = self._build_trigger(job)
            if trigger is None:
                continue
            self._scheduler.add_job(
                self._dispatch_scheduled,
                trigger=trigger,
                id=job.id,
                kwargs={"job_id": job.id},
                misfire_grace_time=self._misfire_grace_seconds,
                coalesce=True,
                max_instances=job.max_concurrent_instances,
                replace_existing=True,
            )
        self._scheduler.start()
        self._started = True

    async def stop(self) -> None:
        """Shut down APScheduler (when started) and await inflight
        runner tasks so the event loop sees them finish cleanly.
        The SHUTDOWN slice adds the 5 s force-terminate (FR-021).

        We always wait for inflight tasks regardless of
        ``_started`` because :meth:`trigger` can spawn runner
        tasks without the APScheduler bootstrap path being
        taken (manual triggers / tests)."""
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
        async with self._inflight_lock:
            tasks = [
                task for tasks in self._inflight.values() for task in tasks
            ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Trigger

    async def await_run(self, job_run_id: int, *, timeout: float = 30.0) -> None:
        """Block until the runner task for ``job_run_id`` has
        completed. Useful from tests / the test endpoint when
        the caller wants to know the runner is done before
        returning a response.

        Production callers (the API trigger endpoint) call
        :meth:`trigger` and return immediately — they don't
        want to hold the request open for a long-running
        runner."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            async with self._inflight_lock:
                inflight = [
                    task
                    for tasks in self._inflight.values()
                    for task in tasks
                    if not task.done()
                    and getattr(task, "_romarr_run_id", None) == job_run_id
                ]
            if not inflight:
                return
            await asyncio.gather(*inflight, return_exceptions=True)

    async def trigger(
        self,
        job_id: str,
        *,
        triggered_by: TriggerKind = TriggerKind.MANUAL,
        triggered_by_user_id: int | None = None,
        parameters: dict[str, Any] | None = None,
        force: bool = False,
    ) -> int:
        """Fire ``job_id`` on demand. Returns the new
        ``job_run.id``.

        Raises:
          * :class:`UnknownJob` — no row in ``job``;
          * :class:`JobDisabled` — ``job.enabled = False``
            (unless ``force=True``);
          * :class:`JobAlreadyRunning` — at
            ``max_concurrent_instances``.

        Auto-pause (FR-018, SC-005): when an ``AutoPause`` is
        wired and reports paused, ``triggered_by=SCHEDULED``
        triggers are silently suppressed (logged at info,
        return -1). Manual / command / event triggers are
        unaffected unless ``force=False`` AND the auto-pause
        gate explicitly applies — but the spec only requires
        the suppression on scheduled ticks (US5.2: manual
        triggers always go through).

        The concurrency check + the JobRun insert + the inflight
        registration are all done while holding ``_inflight_lock``
        so two concurrent triggers can't both pass the cap check.
        """
        if (
            self._auto_pause is not None
            and triggered_by is TriggerKind.SCHEDULED
            and not force
            and await self._auto_pause.is_paused()
        ):
            _logger.info(
                "auto-pause suppressing scheduled trigger: job_id=%s",
                job_id,
            )
            return -1

        async with self._inflight_lock:
            async with self._session_factory() as session:
                job = await session.get(Job, job_id)
                if job is None:
                    raise UnknownJob(f"unknown job: {job_id}")
                if not job.enabled and not force:
                    raise JobDisabled(
                        f"job is disabled: {job_id}"
                    )

                # Drop done tasks so the cap reflects only
                # actually-running runners.
                inflight = self._inflight.setdefault(job.id, set())
                still_running = {t for t in inflight if not t.done()}
                if len(still_running) >= job.max_concurrent_instances:
                    raise JobAlreadyRunning(
                        f"job {job.id} already at "
                        f"max_concurrent_instances={job.max_concurrent_instances}"
                    )
                self._inflight[job.id] = still_running

                run = await start_run(
                    session,
                    job_id=job.id,
                    triggered_by=triggered_by,
                    triggered_by_user_id=triggered_by_user_id,
                )
                await session.commit()
                run_id = run.id

            # Slice 276 — emit ``taskStarted`` to live operator
            # sessions. Best-effort, never blocks dispatch.
            await self._emit_ws(
                "taskStarted",
                {
                    "job_id": job.id,
                    "job_run_id": run_id,
                    "triggered_by": triggered_by.value,
                },
            )

            task = asyncio.create_task(
                self._run_and_finalise(
                    job_id=job_id,
                    job_run_id=run_id,
                    triggered_by=triggered_by,
                    triggered_by_user_id=triggered_by_user_id,
                    parameters=parameters or {},
                ),
                name=f"job-runner-{job_id}-{run_id}",
            )
            # Stamp the task with the run_id so ``await_run`` can
            # find it when the caller wants to block until done.
            task._romarr_run_id = run_id  # type: ignore[attr-defined]
            self._inflight[job_id].add(task)

            def _done(
                completed: asyncio.Task[None],
                _jid: str = job_id,
            ) -> None:
                self._inflight.get(_jid, set()).discard(completed)

            task.add_done_callback(_done)
        return run_id

    # ------------------------------------------------------------------
    # Reschedule (FR-026 / SC-007)

    async def reschedule_job(
        self,
        job_id: str,
        *,
        cron: str | None = None,
        interval_seconds: int | None = None,
    ) -> None:
        """Apply a new schedule without restart.

        Either ``cron`` or ``interval_seconds`` must be set
        (mutually exclusive). The new trigger replaces the old
        one in APScheduler; the next run reflects the new cadence.
        """
        if (cron is None) == (interval_seconds is None):
            raise ScheduleParseError(
                "exactly one of cron / interval_seconds must be set"
            )

        async with self._session_factory() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise UnknownJob(f"unknown job: {job_id}")
            job.schedule_cron = cron
            job.schedule_interval_seconds = interval_seconds
            await session.commit()

        if cron is not None:
            try:
                trigger: CronTrigger | IntervalTrigger = CronTrigger.from_crontab(
                    cron
                )
            except ValueError as exc:
                raise ScheduleParseError(
                    f"invalid cron expression: {cron}"
                ) from exc
        else:
            assert interval_seconds is not None
            if interval_seconds < 30:
                raise ScheduleParseError(
                    "interval_seconds must be >= 30"
                )
            trigger = IntervalTrigger(seconds=interval_seconds)

        self._scheduler.reschedule_job(job_id, trigger=trigger)

    # ------------------------------------------------------------------
    # Internals — runner dispatch + audit

    async def _run_and_finalise(
        self,
        *,
        job_id: str,
        job_run_id: int,
        triggered_by: TriggerKind,
        triggered_by_user_id: int | None,
        parameters: dict[str, Any],
    ) -> None:
        runner = self._runners.get(job_id)
        if runner is None:
            await self._finalise(
                job_run_id=job_run_id,
                status=JobStatus.FAILED,
                error_message=f"no runner registered for job {job_id}",
            )
            return

        cancellation_event = asyncio.Event()
        context = JobContext(
            job_id=job_id,
            job_run_id=job_run_id,
            started_at=datetime.now(UTC),
            triggered_by=triggered_by,
            triggered_by_user_id=triggered_by_user_id,
            progress_callback=lambda _c, _t, _m: None,
            cancellation_event=cancellation_event,
            parameters=dict(parameters),
            # Slice 210: thread the scheduler's session factory
            # through so adapters wired in slices 178-209 can
            # do real DB work instead of falling through to
            # their stub branch when fired by the actual cron.
            sessionmaker=self._session_factory,
            event_channel=self._event_channel,
        )
        # Register with the cancellation registry (when wired)
        # so the cancel-endpoint can signal this run by id.
        # Registration is best-effort — the cancel feature is
        # opt-in at construction time.
        if self._cancellation_registry is not None:
            current_task = asyncio.current_task()
            if current_task is not None:
                await self._cancellation_registry.register(
                    job_run_id=job_run_id,
                    cancellation_event=cancellation_event,
                    task=current_task,
                )

        # Accept both adapter-object runners (`runner.run(ctx)`)
        # and plain async-callable runners (`runner(ctx)`) — the
        # SCHED tests pass closures, the production registry
        # passes adapter instances.
        if hasattr(runner, "run"):
            runner_callable: Any = runner.run
        else:
            runner_callable = runner
        try:
            result = await runner_callable(context)
        except asyncio.CancelledError:
            await self._finalise(
                job_run_id=job_run_id,
                status=JobStatus.CANCELLED,
                error_message=None,
                cancellation_forced=True,
            )
            raise
        except Exception as exc:
            _logger.exception(
                "runner failed: job_id=%s job_run_id=%s",
                job_id,
                job_run_id,
            )
            await self._finalise(
                job_run_id=job_run_id,
                status=JobStatus.FAILED,
                error_message=f"{exc.__class__.__name__}: {exc}",
            )
            return

        await self._finalise(
            job_run_id=job_run_id,
            status=result.status,
            error_message=result.error_message,
            items_processed=result.items_processed,
            output_summary=dict(result.summary),
        )

    async def _emit_ws(self, message_type_name: str, data: dict[str, Any]) -> None:
        """Best-effort WS broadcast — never raises into dispatch.

        ``message_type_name`` is the literal string from the
        ``MessageType`` enum (avoids the import cost when no
        bridge is wired). When the bridge is None, this is a
        cheap no-op.
        """
        if self._ws_bridge is None:
            return
        try:
            from romarr.api.ws.messages import MessageType

            mt = MessageType(message_type_name)
            await self._ws_bridge.emit_message(mt, data=data)
        except Exception:
            _logger.exception(
                "scheduler ws emission failed; envelope dropped"
            )

    async def _finalise(
        self,
        *,
        job_run_id: int,
        status: JobStatus,
        error_message: str | None,
        items_processed: int = 0,
        output_summary: dict[str, Any] | None = None,
        cancellation_forced: bool = False,
    ) -> None:
        async with self._session_factory() as session:
            run = await finish_run(
                session,
                job_run_id=job_run_id,
                status=status,
                items_processed=items_processed,
                output_summary=output_summary,
                error_message=error_message,
                cancellation_forced=cancellation_forced,
            )
            if run is None:
                _logger.warning(
                    "job_run row vanished mid-run: id=%s", job_run_id
                )
                return
            await session.commit()
            job_id = run.job_id
            duration_ms = run.duration_ms

        # Slice 276 — emit ``taskFinished`` to live operator
        # sessions after the row commits. Best-effort.
        await self._emit_ws(
            "taskFinished",
            {
                "job_id": job_id,
                "job_run_id": job_run_id,
                "status": status.value,
                "duration_ms": duration_ms,
                "successful": status == JobStatus.SUCCESS,
                "error_message": error_message,
                "items_processed": items_processed,
            },
        )

    # ------------------------------------------------------------------
    # Internals — APScheduler-side dispatch

    async def _dispatch_scheduled(self, *, job_id: str) -> None:
        """The function APScheduler invokes on the cycle.
        Translates to :meth:`trigger` so cron-fired and manually-
        fired runs share the same audit + concurrency path."""
        try:
            await self.trigger(
                job_id,
                triggered_by=TriggerKind.SCHEDULED,
            )
        except (JobAlreadyRunning, JobDisabled):
            # Steady-state expected on a busy system; log at
            # debug rather than error so the operator UI isn't
            # spammed.
            _logger.debug(
                "scheduled run skipped: job_id=%s reason=concurrency-or-disabled",
                job_id,
            )
        except Exception:
            _logger.exception(
                "scheduled dispatch raised for job_id=%s", job_id
            )

    @staticmethod
    def _build_trigger(
        job: Job,
    ) -> CronTrigger | IntervalTrigger | None:
        if job.schedule_cron:
            try:
                return CronTrigger.from_crontab(job.schedule_cron)
            except ValueError as exc:
                _logger.error(
                    "skipping job %s: invalid cron %r (%s)",
                    job.id,
                    job.schedule_cron,
                    exc,
                )
                return None
        if job.schedule_interval_seconds:
            return IntervalTrigger(
                seconds=job.schedule_interval_seconds
            )
        return None


__all__ = ["JobRegistry", "JobRunner", "SchedulerService"]
