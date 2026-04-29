"""Metadata aggregation layer (spec 002).

Aggregates per-Game metadata from up to 9 external providers into the
canonical :class:`romarr.domain.models.Game` row, respecting per-field
priority lists and ``locked_fields`` (the constitutional anti-RomM-#1770
mechanism).

This package ships in slices: SCAF + PERS first (skeleton, encryption,
3 new tables, cache + covers helpers), then FRAME + AGG (provider ABC +
pure aggregator), then one provider per slice, then the API stubs.
"""

from romarr.metadata.cache import (
    get_cached,
    invalidate_cached,
    put_cached,
)
from romarr.metadata.covers import (
    KNOWN_COVER_EXTENSIONS,
    cover_path_for,
    derive_extension,
    write_cover,
)
from romarr.metadata.encryption import (
    EncryptionKeyMissingError,
    decrypt,
    encrypt,
)
from romarr.metadata.errors import (
    AuthError,
    NotFoundError,
    ProviderError,
    RateLimitError,
    TransientError,
)
from romarr.metadata.types import (
    AggregationResult,
    GameMetadata,
    GameSearchResult,
    ProviderField,
)

__all__ = [
    "KNOWN_COVER_EXTENSIONS",
    "AggregationResult",
    "AuthError",
    "EncryptionKeyMissingError",
    "GameMetadata",
    "GameSearchResult",
    "NotFoundError",
    "ProviderError",
    "ProviderField",
    "RateLimitError",
    "TransientError",
    "cover_path_for",
    "decrypt",
    "derive_extension",
    "encrypt",
    "get_cached",
    "invalidate_cached",
    "put_cached",
    "write_cover",
]
