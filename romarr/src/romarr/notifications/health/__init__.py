"""Health-engine subsystem (spec 011, Phase 7).

Public re-exports for the engine, debouncer, and snapshot.
The per-check classes live under ``health.checks`` and are
imported on demand to keep this module's surface clean.
"""

from romarr.notifications.health.debouncer import (
    Severity,
    Transition,
    compute_transitions,
    should_emit,
)
from romarr.notifications.health.engine import HealthEngine
from romarr.notifications.health.snapshot import build_snapshot

__all__ = [
    "HealthEngine",
    "Severity",
    "Transition",
    "build_snapshot",
    "compute_transitions",
    "should_emit",
]
