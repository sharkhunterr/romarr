"""SteamGridDB metadata provider (FR-005).

Cover-only. The SteamGridDB API exposes much more than covers
(heroes, logos, icons), but for Romarr we only consume cover grids,
and only when the operator manually picks one through the UI's
"swap cover" flow. The standard scan/refresh path explicitly skips
this provider via ``invoked_in_scan=False``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from romarr.metadata.errors import (
    AuthError,
    NotFoundError,
    ProviderError,
    TransientError,
)
from romarr.metadata.providers import register_provider
from romarr.metadata.providers.base import (
    MetadataProvider,
    ProviderCapabilities,
)
from romarr.metadata.types import GameMetadata, GameSearchResult, ProviderField

_BASE = "https://www.steamgriddb.com/api/v2"


class SteamGridDBProvider(MetadataProvider):
    """Cover-only provider — every other method raises NotImplementedError."""

    capabilities = ProviderCapabilities(
        name="steamgriddb",
        requires_auth=True,
        contributable_fields=frozenset({ProviderField.COVER}),
        invoked_in_scan=False,
    )

    def __init__(
        self,
        *,
        rate_limit_rps: int = 5,
        rate_limit_burst: int = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst)
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._owns_client = client is None
        self._api_key: str | None = None

    def configure(self, config: dict[str, Any]) -> None:
        api_key = config.get("api_key")
        if not api_key:
            raise AuthError("SteamGridDB requires an api_key")
        self._api_key = api_key

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health_check(self) -> bool:
        if self._api_key is None:
            return False
        try:
            response = await self._client.get(
                f"{_BASE}/games/id/1",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError:
            return False
        return response.status_code in (200, 404)

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        raise NotImplementedError(
            "SteamGridDB is a cover-only provider; "
            "metadata search is not supported."
        )

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        """Return a metadata stub carrying only the cover URL.

        SteamGridDB doesn't drive scan-flow refreshes, but the
        manual cover-swap endpoint can call ``get_game`` to obtain
        the cover URL before fetching bytes. The returned
        ``GameMetadata`` has ``COVER`` set and nothing else.
        """
        if self._api_key is None:
            raise AuthError("SteamGridDB provider not configured")

        async def _do() -> GameMetadata:
            try:
                response = await self._client.get(
                    f"{_BASE}/grids/game/{provider_game_id}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    params={"types": "static", "limit": 1, "nsfw": "false"},
                )
            except httpx.HTTPError as exc:
                raise TransientError("SteamGridDB network error") from exc
            if response.status_code in (401, 403):
                raise AuthError(f"SteamGridDB {response.status_code}")
            if response.status_code == 404:
                raise NotFoundError(f"SteamGridDB id={provider_game_id} not found")
            if response.status_code >= 500:
                raise TransientError(f"SteamGridDB {response.status_code}")
            if response.status_code != 200:
                raise ProviderError(
                    f"SteamGridDB unexpected {response.status_code}"
                )
            payload = response.json()
            grids = payload.get("data") or []
            if not grids:
                raise NotFoundError(
                    f"SteamGridDB returned no grids for {provider_game_id}"
                )
            cover_url = grids[0].get("url")
            return GameMetadata(
                provider_name=self.name,
                provider_game_id=str(provider_game_id),
                fields={ProviderField.COVER: cover_url} if cover_url else {},
                cover_url=cover_url,
                fetched_at=datetime.now(UTC),
            )

        return await self._call(_do)

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        meta = await self.get_game(provider_game_id)
        if not meta.cover_url:
            raise NotFoundError(f"no cover for SteamGridDB id={provider_game_id}")
        try:
            response = await self._client.get(meta.cover_url)
        except httpx.HTTPError as exc:
            raise TransientError("SteamGridDB CDN network error") from exc
        if response.status_code == 404:
            raise NotFoundError(
                f"SteamGridDB cover 404 for {provider_game_id}"
            )
        if response.status_code >= 500:
            raise TransientError(f"SteamGridDB CDN {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"SteamGridDB CDN {response.status_code}")
        return response.content, response.headers.get("content-type", "image/png")

    def get_platform_mapping(self, platform_slug: str) -> int | str | None:
        # SteamGridDB doesn't have per-platform game ids — the operator
        # picks the SGDB game id directly through the manual flow.
        return None


register_provider("steamgriddb", SteamGridDBProvider)
