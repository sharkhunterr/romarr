"""Profile-gate step (FR-021 / pipeline step 8).

Wraps spec 006's :class:`ProfileEvaluator` so the importer
delegates every accept/reject decision to the same evaluator the
search engine uses. Pure: no I/O, no DB access — the caller
preloads the four profiles plus the :class:`ReleaseFacts`.

Semantics:

  * Every evaluator that returns ``REJECT`` halts the gate and
    surfaces the structured reason.
  * If ``force=True`` (manual flow / FR-021 / US4.2), the rejection
    becomes a ``warning`` rather than a halt — the orchestrator
    still imports but records the warning on the audit row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from romarr.importer.types import RejectionReason
from romarr.profiles.evaluator import evaluate_all
from romarr.profiles.types import Decision

if TYPE_CHECKING:
    from romarr.profiles.types import EvaluationResult, ReleaseFacts


_REJECTION_BY_GATE: dict[str, RejectionReason] = {
    "quality": RejectionReason.PROFILE_QUALITY_REJECT,
    "region": RejectionReason.PROFILE_REGION_REJECT,
    "dump": RejectionReason.PROFILE_DUMP_REJECT,
    "language": RejectionReason.PROFILE_LANGUAGE_REJECT,
}


@dataclass(frozen=True)
class ProfileGateResult:
    """Outcome of the profile gate.

    ``passed`` is ``False`` only when at least one evaluator
    returned REJECT and ``force=False``. When ``force=True``, the
    result still passes but ``warning`` carries the rejection
    reason so the audit row records it (FR-021 / US4.2).

    ``rejection_reason`` is populated whenever a profile said NO,
    regardless of ``force`` — the orchestrator threads it into
    ``import_history.warning`` on force-pass and into
    ``unidentified_dump.rejection_reason`` on hard-reject.
    """

    passed: bool
    rejection_reason: RejectionReason | None = None
    warning: str | None = None
    failing_gate: str | None = None


def apply_profile_gate(
    *,
    quality: object,
    region: object,
    dump: object,
    language: object,
    facts: ReleaseFacts,
    force: bool = False,
) -> ProfileGateResult:
    """Run the four profile evaluators and produce a gate result.

    The gate ordering is fixed (quality → region → dump → language)
    so two reruns over the same inputs always surface the same
    failing gate when more than one would reject.
    """
    results = evaluate_all(
        quality=quality,  # type: ignore[arg-type]
        region=region,  # type: ignore[arg-type]
        dump=dump,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
        facts=facts,
    )
    failure = _first_reject(results)
    if failure is None:
        return ProfileGateResult(passed=True)

    gate_name, _ = failure
    rejection_reason = _REJECTION_BY_GATE[gate_name]

    if force:
        # FR-021 / US4.2: force-import the file but stamp the
        # warning on the audit row.
        return ProfileGateResult(
            passed=True,
            rejection_reason=rejection_reason,
            warning=f"force_overrode:{rejection_reason.value}",
            failing_gate=gate_name,
        )
    return ProfileGateResult(
        passed=False,
        rejection_reason=rejection_reason,
        failing_gate=gate_name,
    )


def _first_reject(
    results: dict[str, EvaluationResult],
) -> tuple[str, EvaluationResult] | None:
    """Return the first gate (in the fixed Q→R→D→L order) whose
    evaluator rejected, or ``None`` if every gate accepted."""
    for gate in ("quality", "region", "dump", "language"):
        result = results[gate]
        if result.decision is Decision.REJECT:
            return gate, result
    return None


__all__ = ["ProfileGateResult", "apply_profile_gate"]
