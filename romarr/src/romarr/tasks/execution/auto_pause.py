"""Auto-pause based on health snapshot (T043, FR-018, SC-005).

When spec 011's :class:`HealthEngine` reports
``overall_status = error``, scheduled job ticks are
suppressed: the indexers / download clients / library mounts
are degraded enough that firing more work makes things worse.
The operator's manual triggers with ``force=True`` are still
allowed (US5.2) — the operator may know better than the
auto-pause heuristic.

The pause is **scheduled-tick only**: in-flight runs continue
to completion (US5.3), and manual triggers with ``force=True``
proceed regardless. The audit log records the suppression so
the operator can see "the scheduler skipped the 12:00 cycle
because of an indexer-error health state."

This module is single-process; each replica reads its own
local :class:`HealthEngine` snapshot.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from romarr.notifications.types import HealthSnapshot

_logger = logging.getLogger(__name__)


# Severity → suppress decision. Per FR-018: ``error`` suppresses
# scheduled ticks. ``warning`` is informational only — the
# operator may still want their RSS sync to fire.
PAUSING_STATUSES: frozenset[str] = frozenset({"error"})


type SnapshotProvider = "Callable[[], Awaitable[HealthSnapshot]]"


class AutoPause:
    """Snapshot-driven gate consulted by the scheduler before
    every dispatch. Cheap to construct — owns no state beyond
    the injected snapshot provider.

    The provider is async so the consumer can call into the
    HealthEngine's `refresh` (or read the persisted snapshot
    via the API path) without holding sync state. Tests pass
    a closure that returns a pre-built snapshot.
    """

    def __init__(
        self,
        *,
        snapshot_provider: SnapshotProvider,
        pausing_statuses: frozenset[str] = PAUSING_STATUSES,
    ) -> None:
        self._snapshot_provider = snapshot_provider
        self._pausing_statuses = pausing_statuses

    async def is_paused(self) -> bool:
        """True iff the latest snapshot's ``overall_status``
        is in :data:`PAUSING_STATUSES`. False on any error
        reading the snapshot — auto-pause is a soft gate, a
        broken health system shouldn't paralyse the scheduler.
        """
        try:
            snapshot = await self._snapshot_provider()
        except Exception:
            _logger.warning(
                "auto-pause snapshot read failed — defaulting to "
                "not-paused so a broken health system doesn't "
                "freeze the scheduler",
                exc_info=True,
            )
            return False
        status_value = snapshot.overall_status.value
        return status_value in self._pausing_statuses


__all__ = ["PAUSING_STATUSES", "AutoPause"]
