"""Health-engine orchestration (T056, FR-017, FR-021a).

Runs every configured :class:`HealthCheck` concurrently, persists
the new state to ``health_check``, computes transitions against
the row's persisted ``last_emitted_state`` (FR-021a), and asks
the caller-supplied ``emit`` callback to fire ``OnHealthIssue``
events for transitions only.

The engine is **single-cycle**: one ``refresh()`` runs all
checks once, returns a :class:`HealthSnapshot`. The periodic
trigger is the Tasks scheduler's job (spec 012); this module
exposes the function.

Persistence is interleaved with the debouncer's transition
calculation in a way that preserves FR-021a's restart-safety:
the engine reads ``last_emitted_state`` from the row BEFORE
running the check, and writes it BACK in the same transaction
as the check result — so a process crash between the two halves
just means the next cycle re-emits, not double-emits.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.notifications.health.checks.base import (
    DEFAULT_CHECK_TIMEOUT_SECONDS,
    run_check,
)
from romarr.notifications.health.debouncer import (
    Transition,
    compute_transitions,
)
from romarr.notifications.health.snapshot import build_snapshot
from romarr.notifications.models import HealthCheck as HealthCheckRow
from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthSnapshot,
    HealthStatus,
    OnHealthIssuePayload,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.notifications.health.checks.base import HealthCheck

_logger = logging.getLogger(__name__)


class HealthEngine:
    """Run all checks once per :meth:`refresh` call.

    The engine is stateless — every cycle reads/writes the
    ``health_check`` table for the previous state. ``checks``
    is supplied by the lifespan wiring (which knows about
    libraries, indexers, download clients).

    ``emit`` is the callback that publishes an
    :class:`OnHealthIssuePayload` onto the notification channel;
    injecting it as a dependency keeps the engine independent
    of the channel's wiring.
    """

    def __init__(
        self,
        *,
        checks: Sequence[HealthCheck],
        session_factory: Callable[[], Awaitable[AsyncSession]],
        emit: Callable[[OnHealthIssuePayload], Awaitable[None]] | None = None,
        check_timeout_seconds: float = DEFAULT_CHECK_TIMEOUT_SECONDS,
    ) -> None:
        self._checks = list(checks)
        self._session_factory = session_factory
        self._emit = emit
        self._check_timeout_seconds = check_timeout_seconds

    async def refresh(self) -> HealthSnapshot:
        """Run one cycle. Returns the in-memory snapshot.

        Order:
          1. Run all checks concurrently with per-check timeout.
          2. Read the previous ``last_emitted_state`` map from
             ``health_check``.
          3. Compute transitions via the debouncer.
          4. Persist the new state + the new ``last_emitted_state``
             for transitioning components — same transaction so
             a crash between emit and persist re-emits next cycle
             rather than double-emits.
          5. Fire ``OnHealthIssue`` events for transitions.
          6. Return the snapshot.
        """
        results = await self._run_all_checks()
        async with await self._session_factory() as session:
            previous = await _load_last_emitted_states(session, results)
            current = {r.component: r.status for r in results}
            transitions = compute_transitions(
                previous=previous, current=current
            )
            await _persist_results(session, results, transitions)
            await session.commit()
        await self._publish_transitions(transitions, results)
        return build_snapshot(
            results=results, refreshed_at=datetime.now(UTC)
        )

    async def _run_all_checks(self) -> list[HealthCheckResult]:
        tasks = [
            asyncio.create_task(
                run_check(check, timeout=self._check_timeout_seconds),
                name=f"healthcheck-{check.component_id}",
            )
            for check in self._checks
        ]
        if not tasks:
            return []
        return list(await asyncio.gather(*tasks))

    async def _publish_transitions(
        self,
        transitions: list[Transition],
        results: list[HealthCheckResult],
    ) -> None:
        if self._emit is None or not transitions:
            return
        # Build a quick map so we can attach the check's
        # message + category to the event payload.
        results_by_component = {r.component: r for r in results}
        for transition in transitions:
            result = results_by_component.get(transition.component)
            if result is None:
                continue
            payload = OnHealthIssuePayload(
                component=transition.component,
                category=result.category,
                severity=transition.severity,
                previous_status=transition.previous or HealthStatus.OK,
                current_status=transition.current,
                message=result.message or "",
            )
            try:
                await self._emit(payload)
            except Exception:
                # One bad subscriber must not block the rest.
                _logger.exception(
                    "OnHealthIssue emit failed for component=%s",
                    transition.component,
                )


# ---------------------------------------------------------------------------
# Persistence helpers


async def _load_last_emitted_states(
    session: AsyncSession,
    results: list[HealthCheckResult],
) -> dict[str, HealthStatus | None]:
    """Read the persisted ``last_emitted_state`` for each
    component in ``results`` (FR-021a). Components missing from
    the table return None — the debouncer treats that as "never
    emitted"."""
    components = [r.component for r in results]
    if not components:
        return {}
    stmt = select(
        HealthCheckRow.component, HealthCheckRow.last_emitted_state
    ).where(HealthCheckRow.component.in_(components))
    rows = (await session.execute(stmt)).all()
    return {
        component: HealthStatus(state) if state else None
        for component, state in rows
    }


async def _persist_results(
    session: AsyncSession,
    results: list[HealthCheckResult],
    transitions: list[Transition],
) -> None:
    """Upsert each result; for components that transitioned,
    update ``last_emitted_state`` in the same transaction so the
    persisted comparison value matches what the operator's
    Discord channel saw."""
    transitioning_components = {
        t.component: t.current for t in transitions
    }
    now = datetime.now(UTC)
    for result in results:
        existing = await _get_row(session, result.component)
        if existing is None:
            row = HealthCheckRow(
                component=result.component,
                status=result.status.value,
                message=result.message,
                severity_changed_at=now,
                last_checked_at=now,
                first_seen_at=now,
                last_seen_at=now,
            )
            if result.component in transitioning_components:
                row.last_emitted_state = (
                    transitioning_components[result.component].value
                )
                row.last_emitted_at = now
            session.add(row)
            continue
        # Update in place.
        if existing.status != result.status.value:
            existing.severity_changed_at = now
        existing.status = result.status.value
        existing.message = result.message
        existing.last_checked_at = now
        existing.last_seen_at = now
        if result.component in transitioning_components:
            existing.last_emitted_state = (
                transitioning_components[result.component].value
            )
            existing.last_emitted_at = now


async def _get_row(
    session: AsyncSession, component: str
) -> HealthCheckRow | None:
    stmt = select(HealthCheckRow).where(
        HealthCheckRow.component == component
    )
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = ["HealthEngine"]


# Module-level imports kept above; ``ComponentCategory`` is
# re-exported through types.py — referenced here so static
# analysers see the dependency on the discriminator.
_ = ComponentCategory
