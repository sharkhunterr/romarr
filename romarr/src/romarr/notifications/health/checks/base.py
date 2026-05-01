"""Health-check Protocol + the per-cycle ``run_check`` runner.

Each check module exposes one or more ``HealthCheck`` instances —
one per component the operator has configured (e.g. one per
indexer, one per library). The engine owns the list of all
checks for the cycle, runs them concurrently with a per-check
timeout (FR-024 — one slow check can't hang the whole cycle),
and writes the aggregated results to ``health_check``.

The :class:`HealthCheck` Protocol is intentionally minimal so a
new check category needs only an async ``run()`` plus stable
``component_id`` / ``category`` fields.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol, runtime_checkable

from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

_logger = logging.getLogger(__name__)

DEFAULT_CHECK_TIMEOUT_SECONDS: float = 10.0
"""Per-check timeout. The engine wraps every check with this so
a hung HTTP probe / DNS query / disk stat can't backpressure the
cycle. FR-024 keeps one slow check from blocking the rest."""


@runtime_checkable
class HealthCheck(Protocol):
    """One probe against one component.

    Implementations build the :class:`HealthCheckResult` and
    return it; raising is fine — :func:`run_check` catches it
    and converts to a structured ``warning`` so a buggy check
    can't crash the cycle.
    """

    component_id: str
    category: ComponentCategory

    async def run(self) -> HealthCheckResult: ...


async def run_check(
    check: HealthCheck,
    *,
    timeout: float = DEFAULT_CHECK_TIMEOUT_SECONDS,
) -> HealthCheckResult:
    """Run ``check.run()`` with a wall-clock timeout.

    A timeout maps to ``warning`` (the engine doesn't know
    whether the component is degraded or just slow); an
    unexpected exception maps to ``error`` with the exception
    class + message in the result. Either way the cycle keeps
    moving — :class:`HealthCheckResult` is always returned.
    """
    try:
        return await asyncio.wait_for(check.run(), timeout=timeout)
    except TimeoutError:
        _logger.warning(
            "health check timed out: component=%s category=%s timeout=%.1fs",
            check.component_id,
            check.category.value,
            timeout,
        )
        return HealthCheckResult(
            component=check.component_id,
            category=check.category,
            status=HealthStatus.WARNING,
            message=f"check exceeded {timeout:.0f}s timeout",
        )
    except Exception as exc:
        _logger.exception(
            "health check raised: component=%s category=%s",
            check.component_id,
            check.category.value,
        )
        return HealthCheckResult(
            component=check.component_id,
            category=check.category,
            status=HealthStatus.ERROR,
            message=f"{exc.__class__.__name__}: {exc}",
        )


__all__ = [
    "DEFAULT_CHECK_TIMEOUT_SECONDS",
    "HealthCheck",
    "run_check",
]
