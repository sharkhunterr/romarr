"""JobRunner Protocol + adapter tests (T025-T026, T030).

Progress-callback throttling (T027) lives in the EXEC slice's
``test_progress.py`` because the throttling logic is a separate
concern from runner dispatch — the EXEC layer wraps the
``progress_callback`` before handing it to the runner.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from romarr.domain import Base
from romarr.tasks.models import Job, JobRun
from romarr.tasks.runner_protocol import (
    JobRunner,
    build_default_registry,
)
from romarr.tasks.runners.adapters import (
    AutoCheckAddedAdapter,
    BackupAdapter,
    CutoffSearchAdapter,
    DatUpdateAdapter,
    HealthCheckAdapter,
    LibraryScanAdapter,
    MissingSearchAdapter,
    RefreshGameMetadataAdapter,
    RssSyncAdapter,
)
from romarr.tasks.scheduler import SchedulerService
from romarr.tasks.types import (
    JobContext,
    JobResult,
    JobStatus,
    TriggerKind,
)


@pytest_asyncio.fixture
async def shared_engine() -> AsyncIterator[AsyncEngine]:
    """Per-test in-memory SQLite with one shared connection.
    See ``test_scheduler.py`` for the rationale (multi-session
    visibility for runner-task writes)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(
    shared_engine: AsyncEngine,
) -> async_sessionmaker:
    return async_sessionmaker(shared_engine, expire_on_commit=False)


def _make_context(
    *,
    job_id: str = "Test",
    parameters: dict[str, object] | None = None,
) -> JobContext:
    return JobContext(
        job_id=job_id,
        job_run_id=1,
        started_at=datetime.now(UTC),
        triggered_by=TriggerKind.MANUAL,
        triggered_by_user_id=None,
        progress_callback=lambda _c, _t, _m: None,
        cancellation_event=asyncio.Event(),
        parameters=parameters or {},
    )


# ---------------------------------------------------------------------------
# T025 — Protocol compliance for every shipped adapter
# ---------------------------------------------------------------------------


_ADAPTERS = [
    RssSyncAdapter,
    CutoffSearchAdapter,
    MissingSearchAdapter,
    RefreshGameMetadataAdapter,
    DatUpdateAdapter,
    BackupAdapter,
    HealthCheckAdapter,
    LibraryScanAdapter,
    AutoCheckAddedAdapter,
]


@pytest.mark.parametrize("adapter_cls", _ADAPTERS)
def test_adapter_satisfies_runner_protocol(adapter_cls: type) -> None:
    """Every adapter is a structurally-typed :class:`JobRunner`
    — has an async ``run(context: JobContext) -> JobResult``."""
    instance = adapter_cls()
    assert isinstance(instance, JobRunner)
    assert hasattr(instance, "run")


@pytest.mark.parametrize("adapter_cls", _ADAPTERS)
def test_adapter_carries_job_id_matching_class(
    adapter_cls: type,
) -> None:
    """Each adapter's ``job_id`` matches the SEED catalogue
    entry it represents."""
    instance = adapter_cls()
    expected = adapter_cls.__name__.removesuffix("Adapter")
    assert instance.job_id == expected


# ---------------------------------------------------------------------------
# T026 — kwargs flow through to the underlying entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_game_metadata_kwargs_flow_through() -> None:
    """``RefreshGameMetadata`` with ``parameters={"gameId": 42}``
    surfaces the gameId in the result summary so the
    operator's UI can confirm the right scope was chosen."""
    adapter = RefreshGameMetadataAdapter()
    context = _make_context(
        job_id="RefreshGameMetadata", parameters={"gameId": 42}
    )
    result = await adapter.run(context)
    assert result.status is JobStatus.SUCCESS
    assert result.summary["scope"] == "single-game"
    assert result.summary["gameId"] == 42


@pytest.mark.asyncio
async def test_refresh_game_metadata_no_kwargs_means_all_games() -> None:
    adapter = RefreshGameMetadataAdapter()
    context = _make_context(
        job_id="RefreshGameMetadata", parameters={}
    )
    result = await adapter.run(context)
    assert result.summary["scope"] == "all-games"
    assert result.summary["gameId"] is None


@pytest.mark.asyncio
async def test_library_scan_kwargs_select_target_library() -> None:
    adapter = LibraryScanAdapter()
    context = _make_context(
        job_id="LibraryScan", parameters={"libraryId": 7}
    )
    result = await adapter.run(context)
    assert "library_id=7" in result.summary["scope"]


# ---------------------------------------------------------------------------
# Health adapter wraps the spec 011 engine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_adapter_calls_engine_refresh() -> None:
    """When wired with a real :class:`HealthEngine`, the adapter
    awaits ``refresh()`` and surfaces the snapshot."""
    from romarr.notifications.types import (
        ComponentCategory,
        HealthSnapshot,
        HealthStatus,
    )

    snapshot = HealthSnapshot(
        overall_status=HealthStatus.OK,
        by_category={ComponentCategory.DB: []},
        refreshed_at=datetime.now(UTC),
    )
    engine = AsyncMock()
    engine.refresh = AsyncMock(return_value=snapshot)

    adapter = HealthCheckAdapter(engine=engine)
    result = await adapter.run(_make_context(job_id="HealthCheck"))

    assert result.status is JobStatus.SUCCESS
    assert result.summary["overall_status"] == "ok"
    assert engine.refresh.await_count == 1


@pytest.mark.asyncio
async def test_health_adapter_without_engine_returns_stub() -> None:
    """Until the lifespan slice wires the real engine, the
    adapter returns a structured stub so the scheduler can
    still bootstrap."""
    adapter = HealthCheckAdapter(engine=None)
    result = await adapter.run(_make_context(job_id="HealthCheck"))
    assert result.status is JobStatus.SUCCESS
    assert result.summary["stub"] is True


# ---------------------------------------------------------------------------
# Adapter exception → JobResult(FAILED) (caught at the adapter layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_exception_surfaces_as_failed() -> None:
    """Custom adapters can raise from their inner ``_run``;
    the base wrapper catches and returns ``FAILED`` with the
    structured error message. Without this, every adapter
    would have to write its own try/except."""

    class BoomAdapter(RssSyncAdapter):  # pyright: ignore[reportInvalidTypeForm]
        async def _run(self, _context: JobContext) -> JobResult:
            raise RuntimeError("kaboom")

    adapter = BoomAdapter()
    result = await adapter.run(_make_context())
    assert result.status is JobStatus.FAILED
    assert "RuntimeError" in (result.error_message or "")
    assert "kaboom" in (result.error_message or "")


# ---------------------------------------------------------------------------
# T030 — registry wires into SchedulerService cleanly
# ---------------------------------------------------------------------------


def test_default_registry_keys_match_seed_catalogue() -> None:
    """Every SEED catalogue entry has a registered runner.
    Catches "added a new factory job but forgot to wire the
    adapter" at import time."""
    from romarr.tasks.seeder import DEFAULT_CATALOGUE

    registry = build_default_registry()
    expected_ids = {default.job_id for default in DEFAULT_CATALOGUE}
    assert set(registry.keys()) == expected_ids


def test_default_registry_values_are_runners() -> None:
    registry = build_default_registry()
    for job_id, runner in registry.items():
        assert isinstance(runner, JobRunner), (
            f"runner for {job_id} doesn't satisfy JobRunner Protocol"
        )


@pytest.mark.asyncio
async def test_scheduler_dispatches_through_registry(
    sessionmaker: async_sessionmaker,
) -> None:
    """End-to-end: SchedulerService looks up the runner from
    the default registry, awaits it, persists the audit row."""
    async with sessionmaker() as session:
        session.add(
            Job(
                id="HealthCheck",
                name="health",
                type="health_check",
                schedule_interval_seconds=600,
            )
        )
        await session.commit()

    service = SchedulerService(
        session_factory=sessionmaker,
        runners=build_default_registry(),
    )
    try:
        run_id = await service.trigger(
            "HealthCheck",
            triggered_by=TriggerKind.MANUAL,
        )
        await service.await_run(run_id)
    finally:
        await service.stop()

    async with sessionmaker() as session:
        run = await session.get(JobRun, run_id)
        assert run is not None
        assert run.status == "success"
        # The HealthCheckAdapter without a wired engine returns
        # the stub summary.
        assert run.output_summary is not None
        assert run.output_summary.get("stub") is True


# ---------------------------------------------------------------------------
# Internals


async def _wait_for_terminal(
    sessionmaker: async_sessionmaker,
    run_id: int,
    *,
    timeout: float = 30.0,
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with sessionmaker() as session:
            run = await session.get(JobRun, run_id)
            if run is not None and run.status != "running":
                return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"job_run {run_id} did not reach terminal within {timeout}s"
    )
