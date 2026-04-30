"""Search-mode round orchestrators (Phase 5).

Five entry points (one per documented mode) consume the pure
pipeline + the state helpers + the indexer registry. The pipeline
is sync and pure; these orchestrators are async — they read from
indexers, the cache, and the database, and they write the resulting
search-history rows.

This slice ships :func:`run_manual_search` and :func:`run_rss_sync` —
the two operator-facing modes. ``on_add`` / ``missing`` /
``cutoff`` schedulers land alongside spec 009's library bindings
(they need a wanted-game query helper that the library spec exposes).
"""

from romarr.search.rounds.manual import run_manual_search
from romarr.search.rounds.rss import run_rss_sync

__all__ = ["run_manual_search", "run_rss_sync"]
