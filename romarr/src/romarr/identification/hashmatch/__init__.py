"""Hash-match cascade — parallel local + Hasheous + PlayMatch lookups.

Public surface:

- :class:`HashMatchCascade` — orchestrates the three backends in
  parallel (FR-026), guards each by a per-service circuit breaker
  (FR-027), and falls back to local-only when both remotes are down
  (FR-028).
- :class:`HashLookupResult` — structured outcome from a single backend.
- :class:`CascadeMatch` — merged outcome with the winning DAT entry,
  supporting matches, and per-backend status flags.
"""

from romarr.identification.hashmatch.cascade import (
    CascadeMatch,
    HashMatchCascade,
)
from romarr.identification.hashmatch.types import (
    BackendName,
    HashLookupResult,
    RemoteHashEntry,
)

__all__ = [
    "BackendName",
    "CascadeMatch",
    "HashLookupResult",
    "HashMatchCascade",
    "RemoteHashEntry",
]
