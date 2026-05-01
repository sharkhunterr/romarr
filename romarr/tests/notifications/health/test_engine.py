"""Health engine cycle tests (T042, FR-017, FR-021a)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from romarr.notifications.health.engine import HealthEngine
from romarr.notifications.models import HealthCheck as HealthCheckRow
from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
    OnHealthIssuePayload,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class _StubCheck:
    """Always returns the configured result."""

    component_id: str
    category: ComponentCategory
    result_status: HealthStatus
    message: str | None = None

    async def run(self) -> HealthCheckResult:
        return HealthCheckResult(
            component=self.component_id,
            category=self.category,
            status=self.result_status,
            message=self.message,
        )


@dataclass
class _CapturingEmitter:
    """Records every OnHealthIssue payload the engine fires."""

    events: list[OnHealthIssuePayload] = field(default_factory=list)

    async def __call__(self, payload: OnHealthIssuePayload) -> None:
        self.events.append(payload)


def _factory_for(
    sessionmaker: async_sessionmaker[AsyncSession],
):
    """Adapter — the engine's session_factory expects an
    awaitable returning an :class:`AsyncSession`. The
    sessionmaker is sync-callable, so we wrap."""

    async def factory() -> AsyncSession:
        return sessionmaker()

    return factory


# ---------------------------------------------------------------------------
# T042 — runs all configured checks and persists per-category results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runs_all_categories(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """One indexer (ok), one download client (ok), one library
    (warning) ⇒ all three components persisted; snapshot's
    ``overall_status`` is the worst-of (warning here)."""
    checks = [
        _StubCheck(
            component_id="indexer:Y",
            category=ComponentCategory.INDEXER,
            result_status=HealthStatus.OK,
        ),
        _StubCheck(
            component_id="downloadclient:qbit",
            category=ComponentCategory.DOWNLOAD_CLIENT,
            result_status=HealthStatus.OK,
        ),
        _StubCheck(
            component_id="library:Cartridges",
            category=ComponentCategory.LIBRARY,
            result_status=HealthStatus.WARNING,
            message="disk getting tight",
        ),
    ]
    emitter = _CapturingEmitter()
    engine = HealthEngine(
        checks=checks,
        session_factory=_factory_for(async_sessionmaker_factory),
        emit=emitter,
    )

    snapshot = await engine.refresh()

    assert snapshot.overall_status is HealthStatus.WARNING
    assert ComponentCategory.INDEXER in snapshot.by_category
    assert ComponentCategory.LIBRARY in snapshot.by_category

    # Persisted rows match.
    async with async_sessionmaker_factory() as session:
        rows = (
            await session.execute(select(HealthCheckRow))
        ).scalars().all()
        components = {row.component: row for row in rows}
    assert "indexer:Y" in components
    assert "downloadclient:qbit" in components
    assert "library:Cartridges" in components
    assert components["library:Cartridges"].status == "warning"
    assert components["library:Cartridges"].last_emitted_state == "warning"

    # Emitter saw exactly one event — the library transition
    # (the two ``ok`` results don't transition from None per
    # FR-021a).
    assert len(emitter.events) == 1
    assert emitter.events[0].component == "library:Cartridges"
    assert emitter.events[0].severity == "warning"


# ---------------------------------------------------------------------------
# FR-021a — second cycle on stable state emits NOTHING
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_cycle_with_no_change_emits_nothing(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    checks = [
        _StubCheck(
            component_id="indexer:Y",
            category=ComponentCategory.INDEXER,
            result_status=HealthStatus.ERROR,
            message="caps unreachable",
        ),
    ]
    emitter = _CapturingEmitter()
    engine = HealthEngine(
        checks=checks,
        session_factory=_factory_for(async_sessionmaker_factory),
        emit=emitter,
    )

    await engine.refresh()
    assert len(emitter.events) == 1  # initial error

    await engine.refresh()
    assert len(emitter.events) == 1  # still 1 — no re-emit (FR-021)


# ---------------------------------------------------------------------------
# FR-021a — recovery cycle emits exactly one event with severity='recovered'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_emits_exactly_one_recovered_event(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    failing = _StubCheck(
        component_id="indexer:Y",
        category=ComponentCategory.INDEXER,
        result_status=HealthStatus.ERROR,
    )
    healthy = _StubCheck(
        component_id="indexer:Y",
        category=ComponentCategory.INDEXER,
        result_status=HealthStatus.OK,
    )
    emitter = _CapturingEmitter()

    engine = HealthEngine(
        checks=[failing],
        session_factory=_factory_for(async_sessionmaker_factory),
        emit=emitter,
    )
    await engine.refresh()  # initial error

    # Swap the check for a healthy one (operator fixed it).
    engine = HealthEngine(
        checks=[healthy],
        session_factory=_factory_for(async_sessionmaker_factory),
        emit=emitter,
    )
    await engine.refresh()  # recovery

    # Two total: one error, one recovered.
    assert len(emitter.events) == 2
    assert emitter.events[1].severity == "recovered"


# ---------------------------------------------------------------------------
# Empty checks list yields an empty snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_check_list_yields_ok_snapshot(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    engine = HealthEngine(
        checks=[],
        session_factory=_factory_for(async_sessionmaker_factory),
        emit=None,
    )
    snapshot = await engine.refresh()
    assert snapshot.overall_status is HealthStatus.OK
    assert snapshot.by_category == {}
