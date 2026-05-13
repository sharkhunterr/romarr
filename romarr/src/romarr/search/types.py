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

from romarr.domain.enums import DumpStatus, NamingConvention  # noqa: TC001


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
    # Resolved facets surfaced on the manual-search row so the
    # operator sees *what* this candidate is (platform, region,
    # languages, dump status, naming convention) without scraping
    # the title. Filled by the pipeline from the SearchResult after
    # the foundation filename parser has run; ``None`` / ``[]``
    # when the parser couldn't recover the field.
    platform_id: int | None = None
    region: str | None = None
    languages: list[str] = Field(default_factory=list)
    dump_status: DumpStatus | None = None
    naming_convention: NamingConvention | None = None
    file_format: str | None = None
    score_breakdown: ScoreBreakdown | None = None
    rejection: Rejection | None = None
    would_auto_reject: bool = False
    pre_grab_dat_match: _DatMatchOutcome = "skipped"
    # Slice 451 — when the cascade matched (outcome="verified" or
    # "hack"), carry the matched ``dat_entry`` row's canonical
    # name + DAT authority so the search modal's row-expand panel
    # can surface *what* the hash matched against, not just *that*
    # it matched. Both stay None for outcome ∈ {none, skipped}.
    pre_grab_dat_entry_name: str | None = None
    pre_grab_dat_entry_source: str | None = None
    # Hashes the indexer shipped on this candidate (lowercase
    # hex). Empty when the indexer / source page didn't expose
    # one. Surfaced in the expand panel so the operator can copy
    # them and cross-reference manually if needed.
    hash_sha1: str | None = None
    hash_md5: str | None = None
    hash_crc32: str | None = None
    # Slice 451 — True iff at least one Dump bound to the matched
    # game already carries an identical hash (SHA-1 / MD5 / CRC32).
    # Drives the "déjà possédé" badge in the search modal so
    # operators don't re-grab a duplicate.
    already_owned: bool = False
    # Identification confidence (0-100). 100 = exact title hit or
    # hash match, ≥ FUZZY_THRESHOLD (85) = fuzzy hit. Surfaces in
    # the manual-search UI as the "title match" half of the
    # operator-facing % score.
    title_match_score: int | None = None

    # Slice 402 — extra indexer metadata projected through from
    # ``SearchResult`` so the search modal's expanded-row view +
    # the scorer can use them. All optional; the parser fills in
    # whatever the torznab/grabarr extended-attrs surfaced.
    grabs: int | None = None
    download_volume_factor: float | None = None
    upload_volume_factor: float | None = None
    description: str | None = None
    year: int | None = None
    genre: str | None = None
    info_url: str | None = None
    nfo_url: str | None = None


_IndexerOutcome = Literal[
    "ok", "failed", "rate_limited", "cache-hit", "cache-miss"
]


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
