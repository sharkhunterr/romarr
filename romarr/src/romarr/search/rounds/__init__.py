"""Search-mode round orchestrators (Phase 5).

Five entry points (one per documented mode) consume the pure
pipeline + the state helpers + the indexer registry. The pipeline
is sync and pure; these orchestrators are async — they read from
indexers, the cache, and the database, and they write the resulting
search-history rows.

The five rounds:

  * :func:`run_manual_search` — one query, one (optional) platform.
  * :func:`run_rss_sync` — RSS feed pull + identification + scoring
    + auto-grab dispatch (slice 224).
  * :func:`run_missing_search` — wanted+monitored Releases probed
    oldest-first (slice 202).
  * :func:`run_cutoff_search` — imported+cutoff_met=false Releases
    (slice 202).
  * :func:`run_search_on_add` — best-effort wrapper around
    ``run_manual_search`` invoked when a new Game lands (slice 181).
"""

from romarr.search.rounds.cutoff import run_cutoff_search
from romarr.search.rounds.manual import run_manual_search
from romarr.search.rounds.missing import run_missing_search
from romarr.search.rounds.on_add import run_search_on_add
from romarr.search.rounds.rss import run_rss_sync

__all__ = [
    "run_cutoff_search",
    "run_manual_search",
    "run_missing_search",
    "run_rss_sync",
    "run_search_on_add",
]
