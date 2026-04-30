"""Search & grab decision engine (spec 007).

Slice 1 ships SCAF + PERS — module skeleton, errors, value types,
SQLAlchemy 2.0 models for the three new tables (``blocklist``,
``search_history``, ``search_cache``), Pydantic
``Read/Create/Update`` schemas, and Alembic migration ``0007``
which also adds ``indexer.rss_auto_grab``.

The pure-function decision pipeline + five round orchestrators +
admin API land in subsequent slices. Public re-exports stay
intentionally thin until those slices land — :func:`run_manual_search`
et al. surface here once their modules exist.
"""

from romarr.search.candidates import select_winners
from romarr.search.errors import (
    BlocklistedReleaseError,
    NoEligibleCandidatesError,
    OverCapWarning,
    SearchError,
)
from romarr.search.matching import FUZZY_THRESHOLD, fuzzy_match_query, resolve_to_game
from romarr.search.pipeline import DAT_VERIFIED_BONUS, run_pipeline
from romarr.search.query_builder import build_queries
from romarr.search.state import (
    BlocklistEntry,
    DatLookup,
    IndexerMeta,
    LibraryState,
    MonitoredGame,
    MonitoredRelease,
    PlatformFormatBounds,
)
from romarr.search.types import (
    Candidate,
    Query,
    Rejection,
    RejectionCode,
    ScoreBreakdown,
    ScoreContribution,
    SearchRoundReport,
    SearchType,
)

__all__ = [
    "DAT_VERIFIED_BONUS",
    "FUZZY_THRESHOLD",
    "BlocklistEntry",
    "BlocklistedReleaseError",
    "Candidate",
    "DatLookup",
    "IndexerMeta",
    "LibraryState",
    "MonitoredGame",
    "MonitoredRelease",
    "NoEligibleCandidatesError",
    "OverCapWarning",
    "PlatformFormatBounds",
    "Query",
    "Rejection",
    "RejectionCode",
    "ScoreBreakdown",
    "ScoreContribution",
    "SearchError",
    "SearchRoundReport",
    "SearchType",
    "build_queries",
    "fuzzy_match_query",
    "resolve_to_game",
    "run_pipeline",
    "select_winners",
]
