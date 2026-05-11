"""MobyGames metadata provider (FR-002).

MobyGames API (https://api.mobygames.com/v1/) authenticates via a
single ``api_key`` query parameter. 403 responses indicate a bad /
missing key (per the docs). The provider contributes title, summary,
genres, release_date, developer, publisher, age_rating — see
:data:`CAPABILITIES`.

The free quota is 360 requests/hour, so the conservative seeded
defaults are 1 rps / burst 2. Operators with paid plans can raise
both knobs via the admin endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from romarr.metadata.errors import (
    AuthError,
    NotFoundError,
    ProviderError,
    RateLimitError,
    TransientError,
)
from romarr.metadata.providers import register_provider
from romarr.metadata.providers.base import (
    MetadataProvider,
    ProviderCapabilities,
)
from romarr.metadata.types import GameMetadata, GameSearchResult, ProviderField

_BASE = "https://api.mobygames.com/v1"

# Slice 411 — MobyGames platform_id mapping, aligned to the
# RomM-canonical Romarr slugs (slice 401). IDs from
# https://www.mobygames.com/info/platforms.
_DEFAULT_PLATFORM_MAPPING: dict[str, int] = {
    "nes": 22,
    "fds": 22,
    "snes": 15,
    "n64": 9,
    "ngc": 14,        # GameCube
    "wii": 82,
    "wiiu": 132,
    "switch": 203,
    "virtualboy": 38,
    "gameboy": 10,
    "gbc": 11,
    "gba": 12,
    "nds": 44,
    "3ds": 101,
    "pokemon-mini": 152,
    "master-system": 26,
    "gamegear": 25,
    "genesis": 16,    # Mega Drive / Genesis
    "segacd": 20,
    "sega32x": 21,
    "saturn": 23,
    "dc": 8,          # Dreamcast
    "psx": 6,
    "ps2": 7,
    "ps3": 81,
    "psp": 46,
    "psvita": 105,
    "xbox": 13,
    "xbox360": 69,
    "atari-2600": 28,
    "atari-5200": 33,
    "atari-7800": 34,
    "atari-jaguar": 17,
    "atari-lynx": 18,
    "neogeo": 36,
    "ngp": 52,
    "ngpc": 53,
    "pcengine": 40,
    "pce-cd": 45,
    "wonderswan": 48,
    "wonderswan-color": 49,
    "colecovision": 29,
    "intellivision": 30,
    "threedo": 35,
}

# MobyGames "genre_category" labels we treat as "genre" for the
# canonical Game.genres list (others — Perspective, Theme, etc. —
# would be re-categorized in a future pass).
_GENRE_CATEGORIES = {"Basic Genres", "Genre", "Sub-Genre"}


class MobyGamesProvider(MetadataProvider):
    capabilities = ProviderCapabilities(
        name="mobygames",
        requires_auth=True,
        contributable_fields=frozenset(
            {
                ProviderField.TITLE,
                ProviderField.SUMMARY,
                ProviderField.GENRES,
                ProviderField.RELEASE_DATE,
                ProviderField.DEVELOPER,
                ProviderField.PUBLISHER,
                ProviderField.AGE_RATING,
                ProviderField.COVER,
                ProviderField.PLAYERS_MIN,
                ProviderField.PLAYERS_MAX,
            }
        ),
    )

    def __init__(
        self,
        *,
        rate_limit_rps: int = 1,
        rate_limit_burst: int = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst)
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._owns_client = client is None
        self._api_key: str | None = None
        self._platform_mapping: dict[str, int] = dict(_DEFAULT_PLATFORM_MAPPING)

    def configure(self, config: dict[str, Any]) -> None:
        api_key = config.get("api_key")
        if not api_key:
            raise AuthError("MobyGames requires an api_key")
        self._api_key = api_key
        if mapping := config.get("platform_mapping"):
            self._platform_mapping = {
                **_DEFAULT_PLATFORM_MAPPING,
                **{str(k): int(v) for k, v in mapping.items()},
            }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _params(self, **extra: Any) -> dict[str, Any]:
        if self._api_key is None:
            raise AuthError("MobyGames provider not configured")
        return {"api_key": self._api_key, "format": "normal", **extra}

    async def health_check(self) -> bool:
        try:
            await self._call(
                lambda: self._get("/genres", params=self._params(limit=1))
            )
        except ProviderError:
            return False
        return True

    async def _get(
        self, path: str, *, params: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(f"{_BASE}{path}", params=params)
        except httpx.HTTPError as exc:
            raise TransientError("MobyGames network error") from exc
        if response.status_code in (401, 403):
            raise AuthError(f"MobyGames {response.status_code}")
        if response.status_code == 404:
            raise NotFoundError(f"MobyGames 404 on {path}")
        if response.status_code == 429:
            raise RateLimitError("MobyGames 429")
        if response.status_code >= 500:
            raise TransientError(f"MobyGames {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"MobyGames unexpected {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover — guard
            raise ProviderError("MobyGames response was not JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderError("MobyGames response was not a JSON object")
        return payload

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        # MobyGames caps `limit` at 100; pull the maximum so all
        # platforms a title shipped on are surfaced.
        params = self._params(title=query, limit=100)
        if platform_slug:
            pid = self._platform_mapping.get(platform_slug)
            if pid is not None:
                params["platform"] = pid

        body = await self._call(lambda: self._get("/games", params=params))
        rows = body.get("games") or []
        out: list[GameSearchResult] = []
        normalized = query.casefold()
        for row in rows:
            title = row.get("title") or ""
            game_id = row.get("game_id")
            if not title or game_id is None:
                continue
            confidence = (
                1.0
                if title.casefold() == normalized
                else 0.85
                if normalized in title.casefold()
                else 0.5
            )
            out.append(
                GameSearchResult(
                    provider_name=self.name,
                    provider_game_id=str(game_id),
                    title=title,
                    confidence=confidence,
                )
            )
        return out

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        body = await self._call(
            lambda: self._get(
                f"/games/{int(provider_game_id)}", params=self._params()
            )
        )
        if not body or not body.get("game_id"):
            raise NotFoundError(
                f"MobyGames has no game with id={provider_game_id}"
            )

        fields: dict[ProviderField, Any] = {}

        if title := body.get("title"):
            fields[ProviderField.TITLE] = title
        if description := body.get("description"):
            fields[ProviderField.SUMMARY] = description

        genres: list[str] = []
        for entry in body.get("genres") or []:
            category = entry.get("genre_category")
            name = entry.get("genre_name")
            if name and (category in _GENRE_CATEGORIES or category is None):
                genres.append(name)
        if genres:
            fields[ProviderField.GENRES] = genres

        # Release date + developer / publisher come from the platform-
        # release sub-array. Pick the earliest first_release_date and
        # the developer / publisher who appears most often across
        # platform releases.
        platforms = body.get("platforms") or []
        release_date, developer, publisher = _pick_release_metadata(platforms)
        if release_date is not None:
            fields[ProviderField.RELEASE_DATE] = release_date
        if developer:
            fields[ProviderField.DEVELOPER] = developer
        if publisher:
            fields[ProviderField.PUBLISHER] = publisher

        # MobyGames age-rating list — pick the ESRB-style entry first.
        for rating in body.get("ratings") or []:
            label = rating.get("rating_name")
            system = rating.get("rating_system_name") or ""
            if label and "ESRB" in system:
                fields[ProviderField.AGE_RATING] = f"ESRB {label}"
                break
            if label and "PEGI" in system:
                fields[ProviderField.AGE_RATING] = f"PEGI {label}"
                break

        cover_url: str | None = None
        sample_cover = body.get("sample_cover") or {}
        if isinstance(sample_cover, dict) and sample_cover.get("image"):
            cover_url = sample_cover["image"]
            fields[ProviderField.COVER] = cover_url

        # Player counts come from the platform-release attributes.
        # Different platform releases may report different ranges; we
        # take the widest reasonable range across all platform entries.
        mn, mx = _pick_player_range(platforms)
        if mn is not None:
            fields[ProviderField.PLAYERS_MIN] = mn
        if mx is not None:
            fields[ProviderField.PLAYERS_MAX] = mx

        return GameMetadata(
            provider_name=self.name,
            provider_game_id=str(provider_game_id),
            fields=fields,
            cover_url=cover_url,
            fetched_at=datetime.now(UTC),
        )

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        meta = await self.get_game(provider_game_id)
        if not meta.cover_url:
            raise NotFoundError(f"no cover for MobyGames id={provider_game_id}")
        try:
            response = await self._client.get(meta.cover_url)
        except httpx.HTTPError as exc:
            raise TransientError("MobyGames CDN network error") from exc
        if response.status_code == 404:
            raise NotFoundError(f"MobyGames cover 404 for {provider_game_id}")
        if response.status_code >= 500:
            raise TransientError(f"MobyGames CDN {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"MobyGames CDN {response.status_code}")
        return response.content, response.headers.get("content-type", "image/jpeg")

    def get_platform_mapping(self, platform_slug: str) -> int | None:
        return self._platform_mapping.get(platform_slug)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _pick_release_metadata(
    platforms: list[dict[str, Any]],
) -> tuple[datetime | None, str | None, str | None]:
    """Pick earliest release_date + most-frequent developer / publisher
    across the platform-release sub-array."""
    earliest: datetime | None = None
    dev_counts: dict[str, int] = {}
    pub_counts: dict[str, int] = {}

    for entry in platforms:
        raw_date = entry.get("first_release_date")
        if raw_date:
            for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
                try:
                    parsed = datetime.strptime(raw_date, fmt).replace(tzinfo=UTC)
                except ValueError:
                    continue
                if earliest is None or parsed < earliest:
                    earliest = parsed
                break

        for company in entry.get("releases") or []:
            for d in company.get("companies") or []:
                role = d.get("role")
                name = d.get("company_name")
                if not name:
                    continue
                if role and "Developed" in role:
                    dev_counts[name] = dev_counts.get(name, 0) + 1
                if role and "Published" in role:
                    pub_counts[name] = pub_counts.get(name, 0) + 1

    developer = max(dev_counts, key=lambda k: dev_counts[k]) if dev_counts else None
    publisher = max(pub_counts, key=lambda k: pub_counts[k]) if pub_counts else None
    return earliest, developer, publisher


def _pick_player_range(
    platforms: list[dict[str, Any]],
) -> tuple[int | None, int | None]:
    """Read the ``Number of Players`` attribute from the first platform
    release that exposes it. Format is free-form like ``"1-4 Players"``."""
    for entry in platforms:
        for attr in entry.get("attributes") or []:
            label = attr.get("attribute_category_name") or ""
            value = attr.get("attribute_name") or ""
            if "Number of Players" in label or "Player" in value:
                mn, mx = _parse_player_range(value)
                if mn is not None or mx is not None:
                    return mn, mx
    return None, None


def _parse_player_range(value: str) -> tuple[int | None, int | None]:
    """``"1-4 Players"`` → (1, 4); ``"2 Players"`` → (2, 2)."""
    digits: list[int] = []
    current = ""
    for ch in value:
        if ch.isdigit():
            current += ch
        elif current:
            digits.append(int(current))
            current = ""
    if current:
        digits.append(int(current))
    if not digits:
        return None, None
    if len(digits) == 1:
        return digits[0], digits[0]
    return min(digits), max(digits)


register_provider("mobygames", MobyGamesProvider)
