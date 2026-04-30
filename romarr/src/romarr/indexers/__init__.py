"""Indexer subsystem (spec 004).

Three things on top of the foundation + platform-packs infrastructure:

  1. A generic Newznab/Torznab HTTP client with extended-attribute
     parsing and per-field provenance.
  2. The Prowlarr application-registration surface
     (``/api/v3/applications``) and the indexer CRUD surface
     (``/api/v3/indexer*``).
  3. Per-indexer rate limiting and circuit breaking — the breaker is
     **imported** from :mod:`romarr.identification.hashmatch.circuit_breaker`
     per Constitution Article III; the rate limiter is new.

This slice ships SCAF + PERS + PARSE. The HTTP client, registry,
connectivity tester, Prowlarr surface, and CRUD endpoints land in
follow-up slices.
"""

from romarr.indexers.errors import (
    IndexerAuthError,
    IndexerError,
    IndexerProtocolError,
    RateLimitDelayed,
)
from romarr.indexers.parser.caps import parse_caps
from romarr.indexers.parser.dedup import dedup_by_guid
from romarr.indexers.parser.extended_attrs import (
    extract_extended_attrs,
    normalize_languages,
    normalize_region,
)
from romarr.indexers.parser.search import parse_search
from romarr.indexers.tokens import (
    generate_token,
    hash_token,
    verify_token,
)
from romarr.indexers.types import (
    DatSource,
    FieldProvenance,
    IndexerCapabilities,
    IndexerHealthIssue,
    ParsedTorznabAttr,
    RssResult,
    SearchResult,
)

__all__ = [
    "DatSource",
    "FieldProvenance",
    "IndexerAuthError",
    "IndexerCapabilities",
    "IndexerError",
    "IndexerHealthIssue",
    "IndexerProtocolError",
    "ParsedTorznabAttr",
    "RateLimitDelayed",
    "RssResult",
    "SearchResult",
    "dedup_by_guid",
    "extract_extended_attrs",
    "generate_token",
    "hash_token",
    "normalize_languages",
    "normalize_region",
    "parse_caps",
    "parse_search",
    "verify_token",
]
