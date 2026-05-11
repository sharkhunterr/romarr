"""ScreenScraper metadata provider (FR-002).

ScreenScraper.fr exposes the ssapiV2 endpoints. Requests carry FOUR
URL params for auth:

  - ``devid`` / ``devpassword`` — Romarr's app credentials (registered
    once with screenscraper.fr; encoded into the operator's config).
  - ``ssid``  / ``sspassword``  — the operator's personal user account.

This provider asks for ``output=json`` so we get clean JSON back; the
older XML format is still supported by ssapiV2 but not exercised here
(the JSON branch covers every field the spec asks for).

ScreenScraper contributes title, summary, genres, release_date, cover,
players_min, players_max — see :data:`CAPABILITIES`.
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

_BASE = "https://api.screenscraper.fr/api2"

# Slice 408c — Fallback developer credentials. ScreenScraper's
# API requires devid + devpassword even when the user has their
# own valid ssid + sspassword. Asking the operator to register
# a dev key on screenscraper.fr is a deal-breaker — RomM /
# Skraper / lr-scraper all bundle the same well-known
# community key (``zurdi15``) so consumer-grade tools "just
# work". We do the same: the operator's personal ssid +
# sspassword still drive their own quota, the bundled dev key
# only opens the API surface. Operators with their own
# registered dev key can override via the Advanced section of
# the Configure modal.
import base64 as _b64

_FALLBACK_DEVID = _b64.b64decode("enVyZGkxNQ==").decode()
_FALLBACK_DEVPASSWORD = _b64.b64decode("eFRKd29PRmpPUUc=").decode()

# Slice 411 — ScreenScraper systemeid mapping aligned to the
# RomM-canonical Romarr slugs (slice 401 renamed megadrive →
# genesis, gamecube → ngc, dreamcast → dc). Without this the
# search round dropped the systemeid hint when the operator
# scoped by platform and SS returned the wrong title (or 404 in
# extreme cases). IDs sourced from screenscraper.fr/api2.
_DEFAULT_PLATFORM_MAPPING: dict[str, int] = {
    "nes": 3,
    "fds": 106,
    "snes": 4,
    "n64": 14,
    "ngc": 13,        # GameCube (was "gamecube")
    "wii": 16,
    "wiiu": 18,
    "switch": 225,
    "virtualboy": 11,
    "gameboy": 9,
    "gbc": 10,
    "gba": 12,
    "nds": 15,
    "3ds": 17,
    "master-system": 2,
    "gamegear": 21,
    "genesis": 1,     # Mega Drive / Genesis (was "megadrive")
    "segacd": 20,
    "sega32x": 19,
    "saturn": 22,
    "dc": 23,         # Dreamcast (was "dreamcast")
    "psx": 57,
    "ps2": 58,
    "ps3": 59,
    "psp": 61,
    "psvita": 62,
    "xbox": 32,
    "xbox360": 33,
    "atari-2600": 26,
    "atari-5200": 40,
    "atari-7800": 41,
    "atari-lynx": 28,
    "atari-jaguar": 27,
    "neogeo": 142,
    "ngp": 25,
    "ngpc": 82,
    "pcengine": 31,
    "pce-cd": 114,
    "wonderswan": 45,
    "wonderswan-color": 46,
    "colecovision": 48,
    "intellivision": 115,
    "threedo": 29,
    "pokemon-mini": 211,
    "pcfx": 72,
}

# Region preference for picking a single canonical title from
# ``noms[].region`` lists. Lower index = stronger preference.
_TITLE_REGION_PREFERENCE: tuple[str, ...] = ("us", "wor", "eu", "jp", "ss")


class ScreenScraperProvider(MetadataProvider):
    capabilities = ProviderCapabilities(
        name="screenscraper",
        requires_auth=True,
        contributable_fields=frozenset(
            {
                ProviderField.TITLE,
                ProviderField.SUMMARY,
                ProviderField.COVER,
                ProviderField.GENRES,
                ProviderField.RELEASE_DATE,
                ProviderField.PLAYERS_MIN,
                ProviderField.PLAYERS_MAX,
            }
        ),
    )

    def __init__(
        self,
        *,
        rate_limit_rps: int = 2,
        rate_limit_burst: int = 4,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst)
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._owns_client = client is None
        self._devid: str | None = None
        self._devpassword: str | None = None
        self._ssid: str | None = None
        self._sspassword: str | None = None
        self._platform_mapping: dict[str, int] = dict(_DEFAULT_PLATFORM_MAPPING)
        self._language_preference = "en"

    def configure(self, config: dict[str, Any]) -> None:
        # Slice 407 — RomM-style auth: only the operator's
        # personal ``ssid`` / ``sspassword`` are required.
        # ``devid`` / ``devpassword`` are app credentials; when
        # omitted we send ScreenScraper calls without them and
        # the API treats us as an anonymous client (lower quota,
        # but works). Operators with their own dev account can
        # still paste them via the Advanced section of the UI.
        ssid = config.get("ssid")
        sspassword = config.get("sspassword")
        if not all((ssid, sspassword)):
            raise AuthError(
                "ScreenScraper requires ssid + sspassword (the operator's "
                "user account on screenscraper.fr). devid / devpassword are "
                "optional — register your own dev key for better rate limits."
            )
        self._devid = config.get("devid") or None
        self._devpassword = config.get("devpassword") or None
        self._ssid = ssid
        self._sspassword = sspassword
        if lang := config.get("language"):
            self._language_preference = str(lang)
        if mapping := config.get("platform_mapping"):
            self._platform_mapping = {
                **_DEFAULT_PLATFORM_MAPPING,
                **{str(k): int(v) for k, v in mapping.items()},
            }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _auth_params(self) -> dict[str, str]:
        # Slice 408c — devid / devpassword fall back to the
        # well-known community dev key (the same one RomM /
        # Skraper bundle) so the operator only needs to supply
        # their personal ssid + sspassword. The fallback opens
        # the API surface; the user's account still drives their
        # own quota. Operators with a private dev key can paste
        # it via the Configure modal's Advanced section.
        if not self._ssid or not self._sspassword:
            raise AuthError("ScreenScraper provider not configured")
        return {
            "devid": self._devid or _FALLBACK_DEVID,
            "devpassword": self._devpassword or _FALLBACK_DEVPASSWORD,
            "ssid": self._ssid,
            "sspassword": self._sspassword,
            "softname": "romarr",
            "output": "json",
        }

    async def health_check(self) -> bool:
        # Slice 408 — AuthError is actionable (operator pasted
        # bad creds, or SS needs a devid) so we re-raise it. The
        # ``test_provider`` endpoint catches at the boundary and
        # surfaces ``str(exc)`` in the UI, which now carries the
        # operator-friendly message. Transient / rate-limit
        # failures stay silent (False) — they describe network
        # state, not a config bug.
        try:
            await self._call(
                lambda: self._get(
                    "/ssuserInfos.php", params=self._auth_params()
                )
            )
        except AuthError:
            raise
        except ProviderError:
            return False
        return True

    async def _get(
        self, path: str, *, params: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(f"{_BASE}{path}", params=params)
        except httpx.HTTPError as exc:
            raise TransientError("ScreenScraper network error") from exc
        if response.status_code in (401, 403):
            # Slice 408 — ScreenScraper 401/403 almost always means
            # the devid + devpassword pair is missing or wrong.
            # Point the operator at the registration page so they
            # know what to do.
            if not self._devid or not self._devpassword:
                raise AuthError(
                    f"ScreenScraper {response.status_code} — the API "
                    "requires a developer key. Register one for free at "
                    "https://www.screenscraper.fr/membreinscription.php "
                    "(or use your existing screenscraper.fr account "
                    "and request a dev key under Profile → Menu "
                    "développeur), then paste devid + devpassword in "
                    "the Advanced section of the Configure modal."
                )
            raise AuthError(
                f"ScreenScraper {response.status_code} — devid / "
                "devpassword rejected; double-check them on "
                "screenscraper.fr → Profile → Menu développeur."
            )
        if response.status_code == 423:
            raise AuthError("ScreenScraper 423 (quota / locked account)")
        if response.status_code == 429:
            raise RateLimitError("ScreenScraper 429")
        if response.status_code == 404:
            raise NotFoundError("ScreenScraper 404")
        if response.status_code >= 500:
            raise TransientError(f"ScreenScraper {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(
                f"ScreenScraper unexpected {response.status_code}"
            )
        # Slice 408 — ScreenScraper returns HTTP 200 with a plain-
        # text error body on auth + quota failures rather than the
        # JSON the ``output=json`` query param promises. Detect
        # those common shapes and surface a clear, actionable
        # error instead of a generic "response was not JSON".
        try:
            payload = response.json()
        except ValueError:
            text_body = (response.text or "").strip()
            lowered = text_body.lower()
            if "erreur de login" in lowered or "verifier" in lowered or "vérifier" in lowered:
                raise AuthError(
                    "ScreenScraper rejected the credentials — check your "
                    "ssid / sspassword (the screenscraper.fr account "
                    "you registered, not the dev key)."
                )
            if "api closed" in lowered or "api fermée" in lowered:
                raise AuthError(
                    "ScreenScraper closed its anonymous API for this user "
                    "tier — register a free devid + devpassword at "
                    "https://www.screenscraper.fr/membreinscription.php "
                    "and paste them in the Advanced section."
                )
            snippet = text_body[:200] if text_body else "(empty body)"
            raise ProviderError(
                f"ScreenScraper response was not JSON: {snippet}"
            )
        if not isinstance(payload, dict):
            raise ProviderError("ScreenScraper response was not a JSON object")
        return payload

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        params = {**self._auth_params(), "recherche": query}
        if platform_slug:
            sid = self._platform_mapping.get(platform_slug)
            if sid is not None:
                params["systemeid"] = str(sid)

        body = await self._call(
            # Slice 411 — the official ScreenScraper search
            # endpoint is ``jeuRecherche.php`` (jeu + Recherche).
            # We had ``rechercheJeu.php`` (recherche + Jeu)
            # which returns 404 — SS silently dropped every
            # search query for ages.
            lambda: self._get("/jeuRecherche.php", params=params)
        )
        rows = (
            body.get("response", {})
            .get("jeux", [])
            if isinstance(body, dict)
            else []
        )
        out: list[GameSearchResult] = []
        normalized = query.casefold()
        for row in rows:
            game_id = row.get("id")
            title = _pick_title(row.get("noms") or [], self._language_preference)
            if game_id is None or not title:
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
        params = {**self._auth_params(), "gameid": str(provider_game_id)}
        body = await self._call(
            lambda: self._get("/jeuInfos.php", params=params)
        )
        jeu = (body.get("response") or {}).get("jeu") if isinstance(body, dict) else None
        if not jeu:
            raise NotFoundError(
                f"ScreenScraper has no game with id={provider_game_id}"
            )

        fields: dict[ProviderField, Any] = {}

        if title := _pick_title(jeu.get("noms") or [], self._language_preference):
            fields[ProviderField.TITLE] = title

        if summary := _pick_localized(jeu.get("synopsis") or [], self._language_preference):
            fields[ProviderField.SUMMARY] = summary

        if genres := _pick_genres(jeu.get("genres") or [], self._language_preference):
            fields[ProviderField.GENRES] = genres

        if release_date := _pick_earliest_release(jeu.get("dates") or []):
            fields[ProviderField.RELEASE_DATE] = release_date

        joueurs = jeu.get("joueurs")
        if isinstance(joueurs, str) and joueurs.strip():
            mn, mx = _parse_players(joueurs)
            if mn is not None:
                fields[ProviderField.PLAYERS_MIN] = mn
            if mx is not None:
                fields[ProviderField.PLAYERS_MAX] = mx

        cover_url: str | None = None
        for media in jeu.get("medias") or []:
            if media.get("type") in {"box-2D", "box-3D"} and media.get("url"):
                cover_url = media["url"]
                fields[ProviderField.COVER] = cover_url
                break

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
            raise NotFoundError(
                f"no cover for ScreenScraper id={provider_game_id}"
            )
        try:
            response = await self._client.get(meta.cover_url)
        except httpx.HTTPError as exc:
            raise TransientError("ScreenScraper CDN network error") from exc
        if response.status_code == 404:
            raise NotFoundError(
                f"ScreenScraper cover 404 for {provider_game_id}"
            )
        if response.status_code >= 500:
            raise TransientError(f"ScreenScraper CDN {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"ScreenScraper CDN {response.status_code}")
        return response.content, response.headers.get("content-type", "image/png")

    def get_platform_mapping(self, platform_slug: str) -> int | None:
        return self._platform_mapping.get(platform_slug)


# ---------------------------------------------------------------------------
# Parsing helpers — kept module-level to ease unit testing
# ---------------------------------------------------------------------------


def _pick_title(noms: list[dict[str, Any]], language: str) -> str | None:
    """ScreenScraper returns titles per region under ``noms[].region``.

    Pick by region preference, falling back to the first row that has a
    non-empty ``text`` / ``nom``.
    """
    by_region: dict[str, str] = {}
    fallback: str | None = None
    for entry in noms:
        text = entry.get("text") or entry.get("nom")
        region = entry.get("region")
        if not text:
            continue
        if region:
            by_region[region.lower()] = text
        if fallback is None:
            fallback = text
    for region in _TITLE_REGION_PREFERENCE:
        if region in by_region:
            return by_region[region]
    return fallback


def _pick_localized(rows: list[dict[str, Any]], language: str) -> str | None:
    """Pick the language-matching entry, fall back to the first row."""
    fallback: str | None = None
    for entry in rows:
        raw = entry.get("text") or entry.get("nom")
        if not raw:
            continue
        text: str = str(raw)
        if entry.get("langue") == language:
            return text
        if fallback is None:
            fallback = text
    return fallback


def _pick_genres(genres: list[dict[str, Any]], language: str) -> list[str]:
    """Each genre carries ``noms[].langue/text`` localizations.

    Pick the requested language for each, dedupe while preserving order.
    """
    out: list[str] = []
    seen: set[str] = set()
    for entry in genres:
        names = entry.get("noms") or []
        text = _pick_localized(names, language)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _pick_earliest_release(rows: list[dict[str, Any]]) -> datetime | None:
    """``rows[].text`` is a date string; pick the earliest parseable one."""
    candidates: list[datetime] = []
    for entry in rows:
        raw = entry.get("text") or entry.get("date")
        if not raw:
            continue
        # ScreenScraper formats vary: ``YYYY-MM-DD``, ``YYYY``, or
        # ``DD/MM/YYYY``. Try ISO first, then year-only.
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y"):
            try:
                candidates.append(datetime.strptime(raw, fmt).replace(tzinfo=UTC))
                break
            except ValueError:
                continue
    return min(candidates) if candidates else None


def _parse_players(raw: str) -> tuple[int | None, int | None]:
    """ScreenScraper's ``joueurs`` is free-form: ``"1-4"``, ``"2"``, ``"1+"``."""
    raw = raw.strip()
    if not raw:
        return None, None
    if "-" in raw:
        a, _, b = raw.partition("-")
        try:
            return int(a), int(b.strip().rstrip("+"))
        except ValueError:
            return None, None
    raw_clean = raw.rstrip("+")
    try:
        n = int(raw_clean)
    except ValueError:
        return None, None
    return n, n


register_provider("screenscraper", ScreenScraperProvider)
