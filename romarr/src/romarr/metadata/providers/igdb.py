"""IGDB metadata provider (FR-002, FR-007a).

Twitch ``client_credentials`` OAuth flow → an in-memory bearer token.
The credentials persisted on ``MetadataProviderConfig.config_encrypted``
are JUST the IGDB Twitch app's ``client_id`` + ``client_secret``; the
bearer is fetched lazily on first use, refreshed on 401, and refreshed
when within 60 s of ``expires_at``. The bearer is NEVER persisted to
disk or DB (FR-007a).

Query language: IGDB v4 takes Apicalypse-style **plain-text POST
bodies** like ``fields *; search "sonic"; where platforms = (29);``.
The HTTP layer is :mod:`httpx` (Article III: no ``requests``).
"""

from __future__ import annotations

import time
from collections.abc import Callable
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
from romarr.metadata.providers.base import MetadataProvider, ProviderCapabilities
from romarr.metadata.types import GameMetadata, GameSearchResult, ProviderField

# Mirror of the foundation 0001 seed for the 5 MVP platforms.
# The configure() call may override this via the ``platform_mapping``
# config key — operators with extra platforms should pass the full map.
_DEFAULT_PLATFORM_MAPPING: dict[str, int] = {
    "nes": 18,
    "snes": 19,
    "megadrive": 29,
    "gameboy": 33,
    "gba": 24,
}

_TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_IGDB_BASE = "https://api.igdb.com/v4"

# IGDB's image base — the trailing image_id maps to a JPG via the
# ``t_cover_big`` size. Spec doesn't pin a size; we use the same one
# RomM picks because it's the largest non-original variant.
_IGDB_IMAGE_BASE = "https://images.igdb.com/igdb/image/upload/t_cover_big"

# IGDB age-rating system → enum mapping (subset RomM uses).
_AGE_RATING_LABELS: dict[int, str] = {
    1: "ESRB E",
    2: "ESRB E10",
    3: "ESRB T",
    4: "ESRB M",
    5: "ESRB AO",
    8: "PEGI 3",
    9: "PEGI 7",
    10: "PEGI 12",
    11: "PEGI 16",
    12: "PEGI 18",
}


class IGDBProvider(MetadataProvider):
    """Concrete provider for IGDB."""

    capabilities = ProviderCapabilities(
        name="igdb",
        requires_auth=True,
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
                ProviderField.THEMES,
                ProviderField.FRANCHISES,
                ProviderField.COVER,
            }
        ),
    )

    def __init__(
        self,
        *,
        rate_limit_rps: int = 4,
        rate_limit_burst: int = 8,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst)
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._owns_client = client is None
        self._clock = clock
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._platform_mapping: dict[str, int] = dict(_DEFAULT_PLATFORM_MAPPING)
        self._bearer: str | None = None
        self._bearer_expires_at: float | None = None  # monotonic seconds

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def configure(self, config: dict[str, Any]) -> None:
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        if not client_id or not client_secret:
            raise AuthError("IGDB requires both client_id and client_secret")
        self._client_id = client_id
        self._client_secret = client_secret
        platform_mapping = config.get("platform_mapping")
        if platform_mapping:
            # Merge over the defaults so partial overrides still work.
            self._platform_mapping = {
                **_DEFAULT_PLATFORM_MAPPING,
                **{str(k): int(v) for k, v in platform_mapping.items()},
            }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        try:
            await self._authed_post("/games", "fields id; limit 1;")
        except ProviderError:
            return False
        return True

    # ------------------------------------------------------------------
    # Search / fetch
    # ------------------------------------------------------------------

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        # IGDB returns each Game once with a list of platform IDs
        # (a single Game can ship on multiple platforms). Romarr's
        # domain model binds a Game to exactly one Platform, so we
        # explode each IGDB hit into one row per (game, platform)
        # pair so the operator picks both the title AND the
        # platform from the search results. We also pull
        # ``first_release_date`` + ``cover.image_id`` so the AddNew
        # page can render year + thumbnail per row.
        body = (
            "fields id, name, slug, platforms, first_release_date, "
            "cover.image_id;"
            f' where name ~ *"{_escape(query)}"*'
        )
        if platform_slug:
            pid = self._platform_mapping.get(platform_slug)
            if pid is not None:
                body += f" & platforms = ({pid})"
        body += "; limit 20;"

        rows = await self._authed_post("/games", body)

        # Reverse the operator-configured platform_mapping so we can
        # turn IGDB's numeric platform ids back into Romarr slugs.
        # Slugs not in the mapping fall through with platform_slug=None
        # so the AddGame modal's platform picker still surfaces.
        igdb_id_to_slug = {
            int(igdb_id): slug
            for slug, igdb_id in self._platform_mapping.items()
        }

        out: list[GameSearchResult] = []
        for row in rows:
            name = row.get("name") or ""
            if not name:
                continue
            confidence = _substring_confidence(query, name)
            release_year: int | None = None
            ts = row.get("first_release_date")
            if ts:
                try:
                    from datetime import UTC, datetime as _dt

                    release_year = _dt.fromtimestamp(int(ts), UTC).year
                except (ValueError, OSError):
                    release_year = None
            cover_url: str | None = None
            cover = row.get("cover")
            if isinstance(cover, dict):
                image_id = cover.get("image_id")
                if image_id:
                    # IGDB's image CDN — `t_cover_small` is the 90x128
                    # pre-cropped thumbnail variant suited to a list row.
                    cover_url = (
                        "https://images.igdb.com/igdb/image/upload/"
                        f"t_cover_small/{image_id}.jpg"
                    )
            platform_ids = row.get("platforms") or []
            if not platform_ids:
                # IGDB row with no platform metadata — emit one
                # generic row.
                out.append(
                    GameSearchResult(
                        provider_name=self.name,
                        provider_game_id=str(row["id"]),
                        title=name,
                        confidence=confidence,
                        release_year=release_year,
                        cover_url=cover_url,
                    )
                )
                continue
            for igdb_pid in platform_ids:
                slug = igdb_id_to_slug.get(int(igdb_pid))
                if slug is None:
                    continue  # unmapped IGDB platform — skip silently
                out.append(
                    GameSearchResult(
                        provider_name=self.name,
                        provider_game_id=str(row["id"]),
                        title=name,
                        confidence=confidence,
                        platform_slug=slug,
                        release_year=release_year,
                        cover_url=cover_url,
                    )
                )
        return out

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        body = (
            "fields name, summary, genres.name, themes.name, franchises.name, "
            "release_dates.date, involved_companies.developer, "
            "involved_companies.publisher, involved_companies.company.name, "
            "rating, age_ratings.rating, cover.image_id; "
            f"where id = ({int(provider_game_id)}); limit 1;"
        )
        rows = await self._authed_post("/games", body)
        if not rows:
            raise NotFoundError(f"IGDB has no game with id={provider_game_id}")
        row = rows[0]

        fields: dict[ProviderField, Any] = {}
        if name := row.get("name"):
            fields[ProviderField.TITLE] = name
        if summary := row.get("summary"):
            fields[ProviderField.SUMMARY] = summary
        if genres := row.get("genres"):
            fields[ProviderField.GENRES] = [g["name"] for g in genres if g.get("name")]
        if themes := row.get("themes"):
            fields[ProviderField.THEMES] = [t["name"] for t in themes if t.get("name")]
        if franchises := row.get("franchises"):
            fields[ProviderField.FRANCHISES] = [
                f["name"] for f in franchises if f.get("name")
            ]
        if rating := row.get("rating"):
            fields[ProviderField.RATING] = float(rating)

        if release_dates := row.get("release_dates"):
            # IGDB stores release_dates[*].date as a Unix timestamp (seconds).
            stamps = [d["date"] for d in release_dates if d.get("date") is not None]
            if stamps:
                first = min(stamps)
                fields[ProviderField.RELEASE_DATE] = datetime.fromtimestamp(
                    first, tz=UTC
                )

        if involved := row.get("involved_companies"):
            for entry in involved:
                company_name = (entry.get("company") or {}).get("name")
                if not company_name:
                    continue
                if entry.get("developer") and ProviderField.DEVELOPER not in fields:
                    fields[ProviderField.DEVELOPER] = company_name
                if entry.get("publisher") and ProviderField.PUBLISHER not in fields:
                    fields[ProviderField.PUBLISHER] = company_name

        if age_ratings := row.get("age_ratings"):
            for entry in age_ratings:
                rating_id = entry.get("rating")
                if rating_id in _AGE_RATING_LABELS:
                    fields[ProviderField.AGE_RATING] = _AGE_RATING_LABELS[rating_id]
                    break

        cover_url: str | None = None
        if cover := row.get("cover"):
            image_id = cover.get("image_id")
            if image_id:
                cover_url = f"{_IGDB_IMAGE_BASE}/{image_id}.jpg"
                fields[ProviderField.COVER] = cover_url

        return GameMetadata(
            provider_name=self.name,
            provider_game_id=str(provider_game_id),
            fields=fields,
            cover_url=cover_url,
            fetched_at=datetime.now(UTC),
        )

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        """Fetch the cover bytes for ``provider_game_id``.

        Cover bytes come from IGDB's static CDN — we don't run them
        through the provider breaker / retry chain because the CDN
        and the API have separate failure modes.
        """
        meta = await self.get_game(provider_game_id)
        if not meta.cover_url:
            raise NotFoundError(f"no cover for IGDB id={provider_game_id}")
        try:
            response = await self._client.get(meta.cover_url)
        except httpx.HTTPError as exc:
            raise TransientError("IGDB CDN network error") from exc
        if response.status_code == 404:
            raise NotFoundError(f"IGDB cover 404 for {provider_game_id}")
        if response.status_code >= 500:
            raise TransientError(f"IGDB CDN {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"IGDB CDN unexpected {response.status_code}")
        return response.content, response.headers.get("content-type", "image/jpeg")

    def get_platform_mapping(self, platform_slug: str) -> int | None:
        return self._platform_mapping.get(platform_slug)

    # ------------------------------------------------------------------
    # Internals — OAuth + HTTP
    # ------------------------------------------------------------------

    async def _ensure_bearer(self, *, force: bool = False) -> str:
        if self._client_id is None or self._client_secret is None:
            raise AuthError("IGDB provider not configured")

        now = self._clock()
        if (
            not force
            and self._bearer is not None
            and self._bearer_expires_at is not None
            and now < self._bearer_expires_at - 60.0
        ):
            return self._bearer

        try:
            response = await self._client.post(
                _TWITCH_TOKEN_URL,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
            )
        except httpx.HTTPError as exc:
            raise TransientError("Twitch OAuth network error") from exc

        if response.status_code in (401, 403):
            raise AuthError(f"Twitch rejected IGDB credentials ({response.status_code})")
        if response.status_code >= 500:
            raise TransientError(f"Twitch OAuth {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"Twitch OAuth unexpected {response.status_code}")

        payload = response.json()
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not token or not isinstance(expires_in, int | float):
            raise AuthError("Twitch OAuth response missing access_token / expires_in")

        bearer = str(token)
        self._bearer = bearer
        self._bearer_expires_at = now + float(expires_in)
        return bearer

    async def _authed_post(self, path: str, body: str) -> list[dict[str, Any]]:
        async def _do() -> list[dict[str, Any]]:
            return await self._post_once(path, body)

        return await self._call(_do)

    async def _post_once(self, path: str, body: str) -> list[dict[str, Any]]:
        token = await self._ensure_bearer()
        try:
            response = await self._client.post(
                f"{_IGDB_BASE}{path}",
                headers={
                    "Client-ID": self._client_id or "",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/plain",
                    "Accept": "application/json",
                },
                content=body,
            )
        except httpx.HTTPError as exc:
            raise TransientError("IGDB network error") from exc

        if response.status_code == 401:
            # Bearer expired in flight — refresh once and retry inline.
            await self._ensure_bearer(force=True)
            try:
                response = await self._client.post(
                    f"{_IGDB_BASE}{path}",
                    headers={
                        "Client-ID": self._client_id or "",
                        "Authorization": f"Bearer {self._bearer or ''}",
                        "Content-Type": "text/plain",
                        "Accept": "application/json",
                    },
                    content=body,
                )
            except httpx.HTTPError as exc:
                raise TransientError("IGDB network error after re-auth") from exc

        if response.status_code in (401, 403):
            raise AuthError(f"IGDB {response.status_code}")
        if response.status_code == 404:
            raise NotFoundError("IGDB 404")
        if response.status_code == 429:
            raise RateLimitError("IGDB 429")
        if response.status_code >= 500:
            raise TransientError(f"IGDB {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"IGDB unexpected {response.status_code}")

        body_json = response.json()
        if not isinstance(body_json, list):
            raise ProviderError("IGDB response was not a JSON array")
        return body_json

def _escape(query: str) -> str:
    """Crude escape for embedding a user query in an IGDB body.

    Escape backslashes first, THEN double-quotes — otherwise the
    quote-escape's backslashes would be re-escaped on the next pass
    and grow without bound.
    """
    return query.replace("\\", "\\\\").replace('"', '\\"')


def _substring_confidence(query: str, name: str) -> float:
    """Cheap confidence: 1.0 on exact-case match, 0.8 on case-insensitive
    exact, 0.5 otherwise (substring hit). Real fuzzy scoring lives in
    the search/decision spec; this is a placeholder."""
    if query == name:
        return 1.0
    if query.lower() == name.lower():
        return 0.8
    return 0.5


register_provider("igdb", IGDBProvider)
