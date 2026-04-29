"""HowLongToBeat metadata provider (FR-007).

Enrichment-only — contributes ``hltb_main`` (the "Main Story"
duration in minutes). Anchors retro-game playthrough estimates so
the UI can surface a "you've got 8 hours of Sonic content" hint.

HLTB has no public, documented API — community Python clients
reverse-engineer the in-page search endpoint at
``https://howlongtobeat.com/api/search``. The endpoint requires a
modern User-Agent and a JSON body with the search query plus a few
filter knobs. Auth is API-key-less; the rotating per-page token that
the community libraries scrape is not yet required for the search
path we exercise here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from romarr.metadata.errors import (
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

_BASE = "https://howlongtobeat.com"

_DEFAULT_HEADERS: dict[str, str] = {
    # HLTB blocks default httpx UA — match a vanilla Chrome string.
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": _BASE,
    "Referer": f"{_BASE}/",
}


class HowLongToBeatProvider(MetadataProvider):
    capabilities = ProviderCapabilities(
        name="howlongtobeat",
        requires_auth=False,
        contributable_fields=frozenset({ProviderField.HLTB_MAIN}),
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

    def configure(self, config: dict[str, Any]) -> None:
        # HLTB has no operator-supplied credentials at MVP — accept and
        # ignore an empty / unused config dict so the registry path is
        # uniform with the auth-needing providers.
        return

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health_check(self) -> bool:
        try:
            await self._search_request(query="zelda")
        except ProviderError:
            return False
        return True

    async def _search_request(self, *, query: str) -> list[dict[str, Any]]:
        body = {
            "searchType": "games",
            "searchTerms": [t for t in query.split() if t],
            "searchPage": 1,
            "size": 20,
            "searchOptions": {
                "games": {
                    "userId": 0,
                    "platform": "",
                    "sortCategory": "popular",
                    "rangeCategory": "main",
                    "rangeTime": {"min": 0, "max": 0},
                    "gameplay": {"perspective": "", "flow": "", "genre": ""},
                    "modifier": "",
                },
                "users": {"sortCategory": "postcount"},
                "filter": "",
                "sort": 0,
                "randomizer": 0,
            },
        }
        try:
            response = await self._client.post(
                f"{_BASE}/api/search",
                headers=_DEFAULT_HEADERS,
                json=body,
            )
        except httpx.HTTPError as exc:
            raise TransientError("HLTB network error") from exc
        if response.status_code in (401, 403):
            raise ProviderError(f"HLTB {response.status_code} (blocked)")
        if response.status_code == 404:
            raise NotFoundError("HLTB search 404")
        if response.status_code >= 500:
            raise TransientError(f"HLTB {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"HLTB unexpected {response.status_code}")
        payload = response.json()
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            return []
        return rows

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        rows = await self._call(lambda: self._search_request(query=query))
        normalized = query.casefold()
        out: list[GameSearchResult] = []
        for row in rows:
            title = row.get("game_name") or ""
            game_id = row.get("game_id")
            if not title or game_id is None:
                continue
            out.append(
                GameSearchResult(
                    provider_name=self.name,
                    provider_game_id=str(game_id),
                    title=title,
                    confidence=1.0 if normalized == title.casefold() else 0.5,
                )
            )
        return out

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        """Fetch the HLTB row by id and return ``hltb_main`` minutes only.

        HLTB's API doesn't expose a "by id" endpoint cleanly; the
        community pattern is to re-search and pick the matching id.
        For MVP we re-query by id formatted as the searchTerm — when
        the search returns a row whose ``game_id`` matches, we read
        its ``comp_main`` field (seconds) and convert to minutes.
        """
        rows = await self._call(
            lambda: self._search_request(query=str(provider_game_id))
        )
        match = None
        for row in rows:
            if str(row.get("game_id")) == str(provider_game_id):
                match = row
                break
        if match is None:
            raise NotFoundError(f"HLTB has no game with id={provider_game_id}")

        seconds = match.get("comp_main")
        fields: dict[ProviderField, Any] = {}
        if isinstance(seconds, int | float) and seconds > 0:
            fields[ProviderField.HLTB_MAIN] = round(seconds / 60)

        return GameMetadata(
            provider_name=self.name,
            provider_game_id=str(provider_game_id),
            fields=fields,
            cover_url=None,
            fetched_at=datetime.now(UTC),
        )

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        raise NotImplementedError(
            "HowLongToBeat doesn't contribute covers."
        )

    def get_platform_mapping(self, platform_slug: str) -> str | None:
        # HLTB scopes by platform name string (e.g. "Sega Mega Drive").
        # Spec 002 doesn't ship a built-in HLTB-platform map; the
        # search endpoint is title-only at MVP.
        return None


register_provider("howlongtobeat", HowLongToBeatProvider)
