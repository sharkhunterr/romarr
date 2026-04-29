"""RetroAchievements metadata provider (FR-006).

Enrichment-only — contributes ``achievements_count`` and nothing else.
RA must NOT be used as a matching source: the canonical Title /
Summary / Genres come from IGDB / MobyGames / ScreenScraper. This
provider's role is purely additive.
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

_BASE = "https://retroachievements.org/API"

# RA's console_id table for Romarr's MVP-5. Source: the GetConsoleIDs
# RA endpoint. Static enough to ship as a built-in.
_DEFAULT_PLATFORM_MAPPING: dict[str, int] = {
    "nes": 7,
    "snes": 3,
    "megadrive": 1,
    "gameboy": 4,
    "gba": 5,
}


class RetroAchievementsProvider(MetadataProvider):
    capabilities = ProviderCapabilities(
        name="retroachievements",
        requires_auth=True,
        contributable_fields=frozenset({ProviderField.ACHIEVEMENTS_COUNT}),
        invoked_in_scan=True,
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
        self._username: str | None = None
        self._api_key: str | None = None
        self._platform_mapping: dict[str, int] = dict(_DEFAULT_PLATFORM_MAPPING)

    def configure(self, config: dict[str, Any]) -> None:
        username = config.get("username")
        api_key = config.get("api_key")
        if not username or not api_key:
            raise AuthError(
                "RetroAchievements requires both username and api_key"
            )
        self._username = username
        self._api_key = api_key
        platform_mapping = config.get("platform_mapping")
        if platform_mapping:
            self._platform_mapping = {
                **_DEFAULT_PLATFORM_MAPPING,
                **{str(k): int(v) for k, v in platform_mapping.items()},
            }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _auth_params(self) -> dict[str, str]:
        if self._username is None or self._api_key is None:
            raise AuthError("RetroAchievements provider not configured")
        return {"z": self._username, "y": self._api_key}

    async def health_check(self) -> bool:
        try:
            await self._call(lambda: self._get("/API_GetConsoleIDs.php"))
        except ProviderError:
            return False
        return True

    async def _get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        merged = {**self._auth_params(), **(params or {})}
        try:
            response = await self._client.get(f"{_BASE}{path}", params=merged)
        except httpx.HTTPError as exc:
            raise TransientError("RA network error") from exc
        if response.status_code in (401, 403):
            raise AuthError(f"RA {response.status_code}")
        if response.status_code == 404:
            raise NotFoundError(f"RA 404 on {path}")
        if response.status_code >= 500:
            raise TransientError(f"RA {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"RA unexpected {response.status_code}")
        return response.json()

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        """Title-search via RA's GetGameList endpoint, scoped to platform.

        RA's catalog is platform-keyed; a platform-less search would
        be ambiguous (the same title appears across N consoles). The
        orchestrator passes ``platform_slug`` from the Game's row.
        """
        if not platform_slug:
            return []
        console_id = self._platform_mapping.get(platform_slug)
        if console_id is None:
            return []

        rows = await self._call(
            lambda: self._get(
                "/API_GetGameList.php",
                params={"i": console_id, "h": 0, "f": 0},
            )
        )
        if not isinstance(rows, list):
            return []

        normalized = query.casefold()
        out: list[GameSearchResult] = []
        for row in rows:
            title = row.get("Title") or ""
            game_id = row.get("ID")
            if not title or game_id is None:
                continue
            if normalized in title.casefold():
                out.append(
                    GameSearchResult(
                        provider_name=self.name,
                        provider_game_id=str(game_id),
                        title=title,
                        confidence=1.0 if normalized == title.casefold() else 0.6,
                    )
                )
        return out

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        payload = await self._call(
            lambda: self._get(
                "/API_GetGame.php",
                params={"i": int(provider_game_id)},
            )
        )
        if not isinstance(payload, dict) or not payload.get("ID"):
            raise NotFoundError(f"RA has no game with id={provider_game_id}")

        # NumAchievements is the canonical count; fall back to len(Achievements)
        # if the field is missing or empty for very-new sets.
        count = payload.get("NumAchievements")
        if count is None:
            achievements = payload.get("Achievements") or []
            count = len(achievements) if isinstance(achievements, list) else 0
        try:
            count_int = int(count)
        except (TypeError, ValueError):
            count_int = 0

        fields: dict[ProviderField, Any] = {}
        if count_int > 0:
            fields[ProviderField.ACHIEVEMENTS_COUNT] = count_int

        return GameMetadata(
            provider_name=self.name,
            provider_game_id=str(provider_game_id),
            fields=fields,
            cover_url=None,
            fetched_at=datetime.now(UTC),
        )

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        raise NotImplementedError(
            "RetroAchievements does not contribute covers; "
            "the canonical cover comes from IGDB / ScreenScraper / SGDB."
        )

    def get_platform_mapping(self, platform_slug: str) -> int | None:
        return self._platform_mapping.get(platform_slug)


register_provider("retroachievements", RetroAchievementsProvider)
