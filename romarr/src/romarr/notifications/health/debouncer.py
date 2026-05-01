"""OnHealthIssue debouncer (FR-021, FR-021a, FR-022, SC-004).

The health engine runs every component check on each refresh
cycle. Without debouncing, a persistently-failing indexer would
emit one ``OnHealthIssue`` event per cycle until the operator
fixed it — within minutes the operator's Discord channel would
be unusable. The debouncer reduces that to **one event per
state transition**: ``ok → warning``, ``ok → error``,
``warning → error``, ``error → warning``, ``warning → ok``
(recovery), ``error → ok`` (recovery).

The transition decision is made against the **persisted**
``health_check.last_emitted_state`` column (FR-021a) so the
suppression survives process restarts. A flapping-then-restarted
Romarr does not re-spam the operator — the engine reads
``last_emitted_state`` from the row before deciding whether to
emit.

This module is **pure**: input is two snapshots (per-component
status), output is the list of transitions that warrant an
emission. The engine handles persistence and event publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from romarr.notifications.types import HealthStatus

# A literal type covering every emission severity the dispatcher
# accepts on ``OnHealthIssuePayload`` (warning / error / recovered).
Severity = Literal["warning", "error", "recovered"]


@dataclass(frozen=True)
class Transition:
    """One state change that warrants an ``OnHealthIssue`` event.

    ``previous`` is the persisted ``last_emitted_state`` (None on
    a brand-new component or after a never-emitted cycle).
    ``current`` is the fresh probe result. ``severity`` is what
    the dispatcher's payload carries.
    """

    component: str
    previous: HealthStatus | None
    current: HealthStatus
    severity: Severity


def compute_transitions(
    *,
    previous: dict[str, HealthStatus | None],
    current: dict[str, HealthStatus],
) -> list[Transition]:
    """Return the list of transitions that should emit events.

    Iterates only over the components present in ``current`` —
    a component disappearing from the engine's check set leaves
    its persisted state alone (the engine's UI / API surface
    handles cleanup). For each component:

      * If ``previous[component]`` is None (never emitted) and
        ``current`` is ``ok``, no emission — the operator
        doesn't need a "I came up healthy" event on first boot.
      * If ``previous[component]`` is None and ``current`` is
        non-ok, emit at the new severity (initial failure).
      * Otherwise, emit only when ``current != previous``.

    The function is total: every input combination produces a
    deterministic output.
    """
    transitions: list[Transition] = []
    for component, current_status in current.items():
        prev_status = previous.get(component)
        severity = _severity_for_transition(prev_status, current_status)
        if severity is None:
            continue
        transitions.append(
            Transition(
                component=component,
                previous=prev_status,
                current=current_status,
                severity=severity,
            )
        )
    return transitions


def _severity_for_transition(
    previous: HealthStatus | None, current: HealthStatus
) -> Severity | None:
    """Return the emission severity, or None when no event fires.

    The state machine:

      None  → ok       : no emission (first cycle, healthy)
      None  → warning  : warning (initial failure)
      None  → error    : error (initial failure)
      ok    → ok       : no emission (steady state)
      ok    → warning  : warning
      ok    → error    : error
      warning → ok     : recovered
      warning → warning: no emission (steady state, FR-021)
      warning → error  : error (escalation, FR-021)
      error → ok       : recovered
      error → warning  : warning (de-escalation)
      error → error    : no emission (steady state, FR-021)
    """
    if previous == current:
        return None
    if current is HealthStatus.OK:
        # Recovery — but only if we previously emitted something
        # non-ok. ``previous is None`` means we never emitted, so
        # no recovery to announce.
        if previous is None:
            return None
        return "recovered"
    if current is HealthStatus.WARNING:
        return "warning"
    if current is HealthStatus.ERROR:
        return "error"
    # Defensive: HealthStatus has only the three members above,
    # but mypy can't prove exhaustiveness without an ``assert``.
    return None


def should_emit(transition: Transition) -> bool:
    """Trivial predicate used by the engine; kept as a public
    name so tests / future filters (mute windows, per-component
    quiet hours) have one place to extend."""
    return transition.severity in ("warning", "error", "recovered")


__all__ = [
    "Severity",
    "Transition",
    "compute_transitions",
    "should_emit",
]
