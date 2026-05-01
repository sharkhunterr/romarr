"""Debouncer transition tests (T050-T052, FR-021/FR-022, SC-004).

The debouncer is the spam-suppression layer for OnHealthIssue
events. These tests lock the FR-021 state machine and the
recovery-event contract.
"""

from __future__ import annotations

from romarr.notifications.health.debouncer import (
    Transition,
    compute_transitions,
    should_emit,
)
from romarr.notifications.types import HealthStatus

# ---------------------------------------------------------------------------
# T050 — same-severity loop emits exactly once (SC-004)
# ---------------------------------------------------------------------------


def test_emit_only_on_transition() -> None:
    """A component that fails identically across 10 cycles emits
    on the first cycle and never again."""
    component = "indexer:slow-tracker"
    # Cycle 1: previous = None, current = error → emit error
    transitions = compute_transitions(
        previous={component: None},
        current={component: HealthStatus.ERROR},
    )
    assert len(transitions) == 1
    assert transitions[0].severity == "error"

    # After emission, the engine writes ``last_emitted_state =
    # error``. Cycles 2-10 pass that as the previous state.
    for _ in range(9):
        transitions = compute_transitions(
            previous={component: HealthStatus.ERROR},
            current={component: HealthStatus.ERROR},
        )
        assert transitions == []


# ---------------------------------------------------------------------------
# T051 — recovery emits exactly one event with severity='recovered'
# ---------------------------------------------------------------------------


def test_recovery_emits_recovered_severity() -> None:
    transitions = compute_transitions(
        previous={"indexer:X": HealthStatus.ERROR},
        current={"indexer:X": HealthStatus.OK},
    )
    assert len(transitions) == 1
    assert transitions[0].severity == "recovered"
    assert transitions[0].current is HealthStatus.OK


def test_recovery_from_warning_also_emits() -> None:
    transitions = compute_transitions(
        previous={"db": HealthStatus.WARNING},
        current={"db": HealthStatus.OK},
    )
    assert len(transitions) == 1
    assert transitions[0].severity == "recovered"


# ---------------------------------------------------------------------------
# T052 — escalation transitions emit one event per transition
# ---------------------------------------------------------------------------


def test_warning_to_error_emits_error() -> None:
    transitions = compute_transitions(
        previous={"indexer:Y": HealthStatus.WARNING},
        current={"indexer:Y": HealthStatus.ERROR},
    )
    assert len(transitions) == 1
    assert transitions[0].severity == "error"


def test_error_to_warning_emits_warning() -> None:
    """De-escalation (a degraded state improving but not yet
    fully healthy) is still a transition worth emitting."""
    transitions = compute_transitions(
        previous={"indexer:Y": HealthStatus.ERROR},
        current={"indexer:Y": HealthStatus.WARNING},
    )
    assert len(transitions) == 1
    assert transitions[0].severity == "warning"


# ---------------------------------------------------------------------------
# FR-021a — first-cycle behavior
# ---------------------------------------------------------------------------


def test_first_cycle_ok_does_not_emit() -> None:
    """A healthy first-ever cycle MUST NOT emit a recovery (or
    anything else). FR-021a's ``None → ok`` rule."""
    transitions = compute_transitions(
        previous={"db": None},
        current={"db": HealthStatus.OK},
    )
    assert transitions == []


def test_first_cycle_warning_emits_initial_failure() -> None:
    transitions = compute_transitions(
        previous={"db": None},
        current={"db": HealthStatus.WARNING},
    )
    assert len(transitions) == 1
    assert transitions[0].severity == "warning"


def test_first_cycle_error_emits_initial_failure() -> None:
    transitions = compute_transitions(
        previous={"db": None},
        current={"db": HealthStatus.ERROR},
    )
    assert len(transitions) == 1
    assert transitions[0].severity == "error"


# ---------------------------------------------------------------------------
# Steady-state cases — never emit
# ---------------------------------------------------------------------------


def test_ok_to_ok_no_emit() -> None:
    transitions = compute_transitions(
        previous={"db": HealthStatus.OK},
        current={"db": HealthStatus.OK},
    )
    assert transitions == []


def test_warning_to_warning_no_emit() -> None:
    transitions = compute_transitions(
        previous={"db": HealthStatus.WARNING},
        current={"db": HealthStatus.WARNING},
    )
    assert transitions == []


def test_error_to_error_no_emit() -> None:
    transitions = compute_transitions(
        previous={"db": HealthStatus.ERROR},
        current={"db": HealthStatus.ERROR},
    )
    assert transitions == []


# ---------------------------------------------------------------------------
# Multi-component independence
# ---------------------------------------------------------------------------


def test_each_component_evaluated_independently() -> None:
    """A flap on one component doesn't bleed into another."""
    transitions = compute_transitions(
        previous={
            "db": HealthStatus.OK,
            "indexer:X": HealthStatus.ERROR,
            "library:Cartridges": None,
        },
        current={
            "db": HealthStatus.OK,  # steady ok → no emit
            "indexer:X": HealthStatus.OK,  # error → ok → recovered
            "library:Cartridges": HealthStatus.WARNING,  # initial failure
        },
    )
    by_component = {t.component: t for t in transitions}
    assert "db" not in by_component
    assert by_component["indexer:X"].severity == "recovered"
    assert by_component["library:Cartridges"].severity == "warning"


# ---------------------------------------------------------------------------
# should_emit predicate
# ---------------------------------------------------------------------------


def test_should_emit_true_for_emitting_severities() -> None:
    for severity in ("warning", "error", "recovered"):
        transition = Transition(
            component="x",
            previous=None,
            current=HealthStatus.WARNING,
            severity=severity,  # type: ignore[arg-type]
        )
        assert should_emit(transition) is True


# ---------------------------------------------------------------------------
# Components missing from current snapshot are not evaluated
# ---------------------------------------------------------------------------


def test_dropped_component_does_not_emit() -> None:
    """A component present in ``previous`` but absent from
    ``current`` isn't evaluated — the engine deletes the row
    elsewhere; the debouncer doesn't synthesize fake events."""
    transitions = compute_transitions(
        previous={"indexer:gone": HealthStatus.ERROR},
        current={},
    )
    assert transitions == []
