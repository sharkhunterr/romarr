"""PlayMatch metadata provider (FR-002).

Same shape as :mod:`romarr.metadata.providers.hasheous`: PlayMatch is
a hash-match service that proxies to IGDB+. The adapter wraps the
existing :class:`romarr.identification.hashmatch.remote.PlayMatchBackend`
client rather than opening its own httpx pool.

PlayMatch's public API is hash-only too, so the adapter is
``invoked_in_scan=False`` and ``search_games`` / ``get_game`` /
``get_cover`` raise NotImplementedError. The hash-driven refresh
endpoint that will exercise these providers lands in a later spec.
"""

from __future__ import annotations

from typing import Any

from romarr.config.settings import get_settings
from romarr.identification.hashmatch.remote import PlayMatchBackend
from romarr.metadata.providers import register_provider
from romarr.metadata.providers.base import (
    MetadataProvider,
    ProviderCapabilities,
)
from romarr.metadata.types import GameMetadata, GameSearchResult, ProviderField


class PlayMatchProvider(MetadataProvider):
    """Thin adapter over :class:`PlayMatchBackend`."""

    capabilities = ProviderCapabilities(
        name="playmatch",
        requires_auth=False,
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
        invoked_in_scan=False,
    )

    def __init__(
        self,
        *,
        rate_limit_rps: int = 5,
        rate_limit_burst: int = 10,
        backend: PlayMatchBackend | None = None,
    ) -> None:
        super().__init__(rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst)
        self._backend = backend or PlayMatchBackend(get_settings())

    @property
    def backend(self) -> PlayMatchBackend:
        """The shared identification client; tests assert it's reused."""
        return self._backend

    def configure(self, config: dict[str, Any]) -> None:
        return

    async def health_check(self) -> bool:
        return True

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        raise NotImplementedError(
            "PlayMatch is a hash-only service; title search is not supported."
        )

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        raise NotImplementedError(
            "PlayMatch is hash-only; ``get_game(provider_game_id)`` "
            "would require an inverse-lookup endpoint that PlayMatch "
            "does not expose."
        )

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        raise NotImplementedError(
            "PlayMatch covers come bundled with the IGDB+ payload its "
            "lookup_sha1 returns; the hash-driven refresh path will "
            "extract them inline."
        )

    def get_platform_mapping(self, platform_slug: str) -> int | None:
        return None


register_provider("playmatch", PlayMatchProvider)
