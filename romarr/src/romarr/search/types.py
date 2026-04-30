"""Value types for the search subsystem.

Pure-Python (no DB, no I/O); consumed by the pipeline, the round
orchestrators, and the API. Persisted entities live in
:mod:`romarr.search.models` + :mod:`romarr.search.schemas`.

The shape is the contract between the pipeline (sync, pure) and
the round orchestrators (async, I/O-bound). Operators see this
shape on the history view + the manual-search response.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RejectionCode(StrEnum):
    """Why a candidate was rejected by the 13-step pipeline.

    Stable strings so the UI can localise + the history view
    can group/filter without fragile string-matching.
    """

    NO_GAME_MATCH = "no_game_match"
    REGION_EXCLUDED = "region_excluded"
    REGION_OUT_OF_PRIORITIES = "region_out_of_priorities"
    LANGUAGE_REQUIRED = "language_required"
    JAPANESE_ONLY_EXCLUDED = "japanese_only_excluded"
    DUMP_STATUS_DISALLOWED = "dump_status_disallowed"
    HACK_DISALLOWED = "hack_disallowed"
    TRAINER_DISALLOWED = "trainer_disallowed"
    TRANSLATION_DISALLOWED = "translation_disallowed"
    PROTO_BETA_DISALLOWED = "proto_beta_disallowed"
    FORMAT_NOT_ALLOWED = "format_not_allowed"
    DAT_REQUIRED = "dat_required"
    CUSTOM_FORMAT_REJECT = "custom_format_reject"
    BLOCKLISTED_GUID = "blocklisted_guid"
    BLOCKLISTED_HASH = "blocklisted_hash"
    SIZE_OUT_OF_BOUNDS = "size_out_of_bounds"
    SEEDERS_BELOW_THRESHOLD = "seeders_below_threshold"


SearchType = Literal["manual", "auto_added", "missing_scheduled", "cutoff_scheduled", "rss"]
"""The five search modes — keeps the search_history.search_type
column's CHECK constraint vocabulary in sync with consumer code."""


_ContributionSource = Literal[
    "region", "language", "custom_format", "dat_match", "size_bonus"
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Rejection(_Base):
    """Pipeline rejection record — one per disqualified candidate."""

    code: RejectionCode
    field: str | None = None
    message: str


class ScoreContribution(_Base):
    """One additive contribution to a candidate's total score.

    ``source`` keeps the contributing subsystem identifiable so the
    UI can group by source ("region: USA First +4, custom_format:
    Verified Dump +100, size_bonus: -10").
    """

    source: _ContributionSource
    name: str
    value: int


class ScoreBreakdown(_Base):
    """Total + individual contributions — the "why" of a score.

    ``total`` MUST equal ``sum(c.value for c in contributions)``;
    the pipeline + tests both enforce that invariant.
    """

    total: int
    contributions: list[ScoreContribution] = Field(default_factory=list)


_DatMatchOutcome = Literal["verified", "hack", "none", "skipped"]


class Candidate(_Base):
    """One indexer result projected through the pipeline.

    Either ``score_breakdown`` or ``rejection`` is populated, never
    both. ``would_auto_reject`` is the convenience flag the manual
    UI consults to render rejected candidates as greyed-out without
    introspecting ``rejection``.
    """

    indexer_id: int
    indexer_guid: str
    title: str
    download_url: str
    size_bytes: int | None = None
    seeders: int | None = None
    matched_game_id: int | None = None
    matched_release_id: int | None = None
    score_breakdown: ScoreBreakdown | None = None
    rejection: Rejection | None = None
    would_auto_reject: bool = False
    pre_grab_dat_match: _DatMatchOutcome = "skipped"


_IndexerOutcome = Literal["ok", "failed", "cache-hit", "cache-miss"]


class SearchRoundReport(_Base):
    """The top-level result of one search-mode round.

    Carries every parsed candidate (rejected included) so the UI
    history view can show the full picture, plus the subset that
    won and were dispatched. ``overcap_indexers`` lists indexers
    whose responses exceeded FR-029's hard cap and were truncated.
    """

    correlation_id: UUID
    search_type: SearchType
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    grabs: list[Candidate] = Field(default_factory=list)
    indexer_outcomes: dict[int, _IndexerOutcome] = Field(default_factory=dict)
    overcap_indexers: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal pipeline value types — not part of the public API
# ---------------------------------------------------------------------------


class Query(_Base):
    """One query string the search builder hands to an indexer.

    ``label`` distinguishes the four documented variants from FR-006:
    canonical / alt-name / canonical+platform / canonical+manufacturer.
    The history view shows the label so the operator sees which
    variant matched.
    """

    text: str
    label: Literal[
        "canonical",
        "alt_name",
        "with_platform",
        "with_manufacturer",
    ]


__all__ = [
    "Candidate",
    "Query",
    "Rejection",
    "RejectionCode",
    "ScoreBreakdown",
    "ScoreContribution",
    "SearchRoundReport",
    "SearchType",
]
