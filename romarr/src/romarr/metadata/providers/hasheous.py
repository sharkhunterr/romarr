"""Hasheous metadata provider (FR-002).

Hasheous is a hash-match service that proxies to IGDB+. Per the plan
("Identification-side Reuse"), this metadata adapter wraps the existing
:class:`romarr.identification.hashmatch.remote.HasheousBackend` client
rather than opening its own httpx connection pool.

Hasheous is NOT a title-search service — its public API only takes a
ROM hash. The adapter therefore disables the standard title-driven
refresh path (``invoked_in_scan=False``); a future hash-driven refresh
endpoint will dispatch into Hasheous directly via its native
``lookup_sha1`` API.

The provider is still registered (and exposed via the registry) so
operators can configure rate-limits / TTL / health-check it from the
admin UI exactly like the other providers.
"""

from __future__ import annotations

from typing import Any

from romarr.config.settings import get_settings
from romarr.identification.hashmatch.remote import HasheousBackend
from romarr.metadata.providers import register_provider
from romarr.metadata.providers.base import (
    MetadataProvider,
    ProviderCapabilities,
)
from romarr.metadata.types import GameMetadata, GameSearchResult, ProviderField


class HasheousProvider(MetadataProvider):
    """Thin adapter over :class:`HasheousBackend`.

    The underlying httpx client is owned by the identification
    backend; this adapter holds a *reference*, not a fresh pool.
    """

    capabilities = ProviderCapabilities(
        name="hasheous",
        requires_auth=False,
        # Hasheous proxies to IGDB+ so its hash payload contains the
        # same field set IGDB does. Mark them so the aggregator can
        # rank Hasheous as a hash-driven fallback when an operator
        # wires it into field_priority.
        contributable_fields=frozenset(
            {
                ProviderField.TITLE,
                ProviderField.SUMMARY,
                ProviderField.GENRES,
                ProviderField.RELEASE_DATE,
                ProviderField.DEVELOPER,
                ProviderField.PUBLISHER,
                ProviderField.RATING,
                ProviderField.AGE_RATING,
                ProviderField.COVER,
            }
        ),
        # Hash-only API — title-driven refresh skips this provider.
        invoked_in_scan=False,
    )

    def __init__(
        self,
        *,
        rate_limit_rps: int = 5,
        rate_limit_burst: int = 10,
        backend: HasheousBackend | None = None,
    ) -> None:
        super().__init__(rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst)
        # Hold a reference to the existing identification-layer client.
        # Per Article III (no duplicated breaker library / HTTP pool):
        # this adapter MUST NOT open its own httpx.AsyncClient.
        self._backend = backend or HasheousBackend(get_settings())

    @property
    def backend(self) -> HasheousBackend:
        """The shared identification client; tests assert it's reused."""
        return self._backend

    def configure(self, config: dict[str, Any]) -> None:
        # Hasheous credentials live on Settings (ROMARR_HASHEOUS_TOKEN)
        # — see foundation FR-026a. The metadata-side config blob is
        # accepted but currently unused; reserving the slot lets a
        # future spec migrate the token here without breaking callers.
        return

    async def health_check(self) -> bool:
        # The identification backend doesn't expose a non-hash probe;
        # an empty / dummy SHA1 lookup returns 404 which we treat as
        # "reachable but no match" → healthy. Real reachability tests
        # will land alongside the hash-driven refresh endpoint.
        return True

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        raise NotImplementedError(
            "Hasheous is a hash-only service; title search is not supported. "
            "Use the hash-driven refresh path once it lands."
        )

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        raise NotImplementedError(
            "Hasheous is hash-only; ``get_game(provider_game_id)`` "
            "would require an inverse-lookup endpoint that Hasheous "
            "does not expose."
        )

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        raise NotImplementedError(
            "Hasheous covers come bundled with the IGDB+ payload its "
            "lookup_sha1 returns; the hash-driven refresh path will "
            "extract them inline rather than calling get_cover()."
        )

    def get_platform_mapping(self, platform_slug: str) -> int | None:
        # Hasheous keys on IGDB platform ids internally — operators
        # configure these on the identification-side Settings, not here.
        return None


register_provider("hasheous", HasheousProvider)
