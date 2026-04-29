"""Metadata aggregation layer (spec 002).

Aggregates per-Game metadata from up to 9 external providers into the
canonical :class:`romarr.domain.models.Game` row, respecting per-field
priority lists and ``locked_fields`` (the constitutional anti-RomM-#1770
mechanism).

This package ships in slices: SCAF + PERS first (skeleton, encryption,
3 new tables, cache + covers helpers), then FRAME + AGG (provider ABC +
pure aggregator), then one provider per slice, then the API stubs.
"""

from romarr.metadata.aggregator import aggregate
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
from romarr.metadata.providers import (
    PROVIDER_REGISTRY,
    MetadataProvider,
    ProviderCapabilities,
    register_provider,
)

# Side-effect imports: each provider module registers itself in
# PROVIDER_REGISTRY at import time. Adding a provider in a future
# slice means dropping its module here AND adding the test under
# tests/metadata/providers/.
from romarr.metadata.providers import howlongtobeat as _howlongtobeat  # noqa: F401
from romarr.metadata.providers import igdb as _igdb  # noqa: F401
from romarr.metadata.providers import retroachievements as _retroachievements  # noqa: F401
from romarr.metadata.providers import steamgriddb as _steamgriddb  # noqa: F401
from romarr.metadata.refresh import refresh_game_metadata
from romarr.metadata.registry import load_enabled_providers
from romarr.metadata.types import (
    AggregationResult,
    GameMetadata,
    GameSearchResult,
    ProviderField,
)

__all__ = [
    "KNOWN_COVER_EXTENSIONS",
    "PROVIDER_REGISTRY",
    "AggregationResult",
    "AuthError",
    "EncryptionKeyMissingError",
    "GameMetadata",
    "GameSearchResult",
    "MetadataProvider",
    "NotFoundError",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderField",
    "RateLimitError",
    "TransientError",
    "aggregate",
    "cover_path_for",
    "decrypt",
    "derive_extension",
    "encrypt",
    "get_cached",
    "invalidate_cached",
    "load_enabled_providers",
    "put_cached",
    "refresh_game_metadata",
    "register_provider",
    "write_cover",
]
