"""Value types for the profiles feature.

Pure-Python (no DB, no I/O); consumed by the evaluator, the scoring
engine, and the API. Persisted entities live in
:mod:`romarr.profiles.models` + :mod:`romarr.profiles.schemas`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Decision(StrEnum):
    """Three-way outcome of one evaluator call.

    NEUTRAL is reserved for evaluators that have no opinion (e.g.,
    a Region profile with empty ``priorities`` and fallback enabled
    treats every region neutrally — the search engine breaks ties
    on score alone).
    """

    ACCEPT = "accept"
    REJECT = "reject"
    NEUTRAL = "neutral"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvaluationReason(_Base):
    """Why the evaluator returned the decision it did.

    ``code`` is machine-readable so the UI can localise; ``message``
    is the developer-facing English string ready to log.
    """

    field: str | None = None
    code: str
    message: str


class EvaluationResult(_Base):
    """Outcome of one evaluator call.

    ``score`` is populated by the Region evaluator (rank score, see
    FR-013) and by the Custom Format scorer (sum of matching format
    scores). The other evaluators return ``score=0`` — they're pure
    accept/reject filters.
    """

    decision: Decision
    reason: EvaluationReason | None = None
    score: int = 0


class NamingPreviewResponse(_Base):
    """Response body for the naming-template ``/preview`` endpoint."""

    rendered: str


class ForceDeleteResult(_Base):
    """Response body for ``DELETE /api/v3/<type>profile/{id}?force=true``."""

    deleted: bool
    affected_libraries: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Custom Format condition value types
# ---------------------------------------------------------------------------


_CONDITION_FIELD = Literal[
    "tags",
    "region",
    "format",
    "dump_status",
    "release_group",
    "indexer_source",
    "languages",
    "revision",
    "naming_convention",
    "release_size",
]


_CONDITION_OPERATOR = Literal[
    "matches_regex",
    "equals",
    "in",
    "contains",
    "not_in",
    "greater_than",
    "less_than",
]


__all__ = [
    "Decision",
    "EvaluationReason",
    "EvaluationResult",
    "ForceDeleteResult",
    "NamingPreviewResponse",
]
