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

from romarr.search.blocklist import (
    add_entry as blocklist_add_entry,
)
from romarr.search.blocklist import (
    auto_add_on_import_failure as blocklist_auto_add_on_import_failure,
)
from romarr.search.blocklist import (
    delete_entry as blocklist_delete_entry,
)
from romarr.search.blocklist import (
    is_blocklisted,
)
from romarr.search.cache import (
    cache_key_for,
    get_cached,
    put_cached,
)
from romarr.search.cache import (
    invalidate as invalidate_cached,
)
from romarr.search.candidates import select_winners
from romarr.search.dispatch import (
    DispatchOutcome,
    DispatchStatus,
    dispatch_winner,
)
from romarr.search.errors import (
    BlocklistedReleaseError,
    NoEligibleCandidatesError,
    OverCapWarning,
    SearchError,
)
from romarr.search.history import record_round as record_history_round
from romarr.search.matching import FUZZY_THRESHOLD, fuzzy_match_query, resolve_to_game
from romarr.search.pipeline import DAT_VERIFIED_BONUS, run_pipeline
from romarr.search.query_builder import build_queries
from romarr.search.rounds import run_manual_search, run_rss_sync
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
    "DispatchOutcome",
    "DispatchStatus",
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
    "blocklist_add_entry",
    "blocklist_auto_add_on_import_failure",
    "blocklist_delete_entry",
    "build_queries",
    "cache_key_for",
    "dispatch_winner",
    "fuzzy_match_query",
    "get_cached",
    "invalidate_cached",
    "is_blocklisted",
    "put_cached",
    "record_history_round",
    "resolve_to_game",
    "run_manual_search",
    "run_pipeline",
    "run_rss_sync",
    "select_winners",
]
