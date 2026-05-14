"""LaunchBox Games Database metadata provider (FR-002).

LaunchBox doesn't expose a documented public REST API. The community
maintains a 200 MB XML archive at
``https://gamesdb.launchbox-app.com/Metadata.zip`` that operators can
download out-of-band. Per the plan's Phase 0 research:

  > Skip [bulk XML import] in MVP. The bulk archive is ~200 MB and the
  > per-Game query path is enough for the constitutional acceptance bar.
  > Define the import interface (``LaunchBoxBulkImporter``) so the v1
  > spec can drop in the implementation.

This module ships:

  - A tiny in-memory cache (``dict[str, dict]`` keyed by lowercased
    title) that the per-Game query path reads from.
  - :class:`LaunchBoxBulkImporter`, a NotImplementedError stub whose
    interface is locked in so a v1 implementation can drop in without
    breaking spec-002 callers.

When the cache is empty (no operator-side import has run yet),
``search_games`` returns an empty list — the orchestrator treats that
the same as "provider had no match" and moves on.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from romarr.metadata.errors import (
    NotFoundError,
)
from romarr.metadata.providers import register_provider
from romarr.metadata.providers.base import (
    MetadataProvider,
    ProviderCapabilities,
)
from romarr.metadata.types import GameMetadata, GameSearchResult, ProviderField

# Slice 411 — LaunchBox bulk-XML platform name mapping, aligned
# to the RomM-canonical Romarr slugs (slice 401: megadrive →
# genesis, gamecube → ngc, dreamcast → dc). Used by the
# (deferred) bulk importer to find each platform's section in
# the LB XML dump.
_DEFAULT_PLATFORM_MAPPING: dict[str, str] = {
    "nes": "Nintendo Entertainment System",
    "fds": "Famicom Disk System",
    "snes": "Super Nintendo Entertainment System",
    "n64": "Nintendo 64",
    "ngc": "Nintendo GameCube",
    "wii": "Nintendo Wii",
    "wiiu": "Nintendo Wii U",
    "switch": "Nintendo Switch",
    "virtualboy": "Nintendo Virtual Boy",
    "gb": "Nintendo Game Boy",
    "gbc": "Nintendo Game Boy Color",
    "gba": "Nintendo Game Boy Advance",
    "nds": "Nintendo DS",
    "3ds": "Nintendo 3DS",
    "pokemon-mini": "Nintendo Pokemon Mini",
    "master-system": "Sega Master System",
    "gamegear": "Sega Game Gear",
    "genesis": "Sega Genesis",
    "segacd": "Sega CD",
    "sega32x": "Sega 32X",
    "saturn": "Sega Saturn",
    "dc": "Sega Dreamcast",
    "psx": "Sony Playstation",
    "ps2": "Sony Playstation 2",
    "ps3": "Sony Playstation 3",
    "psp": "Sony PSP",
    "psvita": "Sony Playstation Vita",
    "xbox": "Microsoft Xbox",
    "xbox360": "Microsoft Xbox 360",
    "atari-2600": "Atari 2600",
    "atari-5200": "Atari 5200",
    "atari-7800": "Atari 7800",
    "atari-jaguar": "Atari Jaguar",
    "atari-lynx": "Atari Lynx",
    "neogeo": "SNK Neo Geo AES",
    "ngp": "SNK Neo Geo Pocket",
    "ngpc": "SNK Neo Geo Pocket Color",
    "pcengine": "NEC TurboGrafx-16",
    "pce-cd": "NEC TurboGrafx-CD",
    "wonderswan": "WonderSwan",
    "wonderswan-color": "WonderSwan Color",
    "colecovision": "ColecoVision",
    "intellivision": "Mattel Intellivision",
    "threedo": "3DO Interactive Multiplayer",
}


class LaunchBoxBulkImporter:
    """Interface stub for the LaunchBox bulk-XML importer.

    Operators run this once after dropping ``Metadata.zip`` into a
    configured path. The MVP raises :class:`NotImplementedError` — the
    real implementation lands in v1.

    The interface is documented here so callers in spec 002 / future
    specs (Library, Tasks/Scheduler) can compose against it without
    waiting on the full implementation.
    """

    def __init__(
        self,
        archive_path: Path,
        *,
        cache: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.archive_path = Path(archive_path)
        self._cache = cache

    async def run(self) -> int:  # pragma: no cover — stub
        """Parse the LaunchBox XML and populate the cache. Returns row count."""
        raise NotImplementedError(
            "LaunchBox bulk XML import is deferred to v1 per spec 002 plan "
            "Phase 0 research. The interface is locked in here so a v1 "
            "implementation can drop in transparently."
        )


class LaunchBoxProvider(MetadataProvider):
    capabilities = ProviderCapabilities(
        name="launchbox",
        requires_auth=False,
        contributable_fields=frozenset(
            {
                ProviderField.TITLE,
                ProviderField.SUMMARY,
                ProviderField.COVER,
                ProviderField.GENRES,
                ProviderField.RELEASE_DATE,
                ProviderField.DEVELOPER,
                ProviderField.PUBLISHER,
            }
        ),
    )

    def __init__(
        self,
        *,
        rate_limit_rps: int = 5,
        rate_limit_burst: int = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst)
        # The HTTP client is unused at MVP — the per-Game query path
        # reads from an in-memory cache populated by the bulk importer.
        # Hold the client anyway so the v1 path that fetches updates
        # incrementally over HTTP doesn't need a constructor change.
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._owns_client = client is None
        self._platform_mapping: dict[str, str] = dict(_DEFAULT_PLATFORM_MAPPING)
        # ``_cache[normalized_title]`` → ``dict`` matching the LB row
        # shape: id, title, platform, year, summary, developer,
        # publisher, genres, cover_url. Populated by the importer.
        self._cache: dict[str, dict[str, Any]] = {}

    def configure(self, config: dict[str, Any]) -> None:
        if mapping := config.get("platform_mapping"):
            self._platform_mapping = {
                **_DEFAULT_PLATFORM_MAPPING,
                **{str(k): str(v) for k, v in mapping.items()},
            }
        # Operators can pre-populate the cache via the config blob —
        # useful for tests and for a one-line "import these 5 games
        # from the LB archive" recipe before the full importer ships.
        if seed := config.get("cache"):
            for title, row in (seed or {}).items():
                self._cache[title.casefold()] = dict(row)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health_check(self) -> bool:
        # Cache-only at MVP — the provider is "healthy" when the cache
        # has at least one row. An empty cache is the legitimate
        # "operator hasn't imported yet" state.
        return bool(self._cache)

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        normalized = query.casefold()
        wanted_platform = (
            self._platform_mapping.get(platform_slug) if platform_slug else None
        )
        out: list[GameSearchResult] = []
        for title_key, row in self._cache.items():
            if normalized not in title_key:
                continue
            if wanted_platform and row.get("platform") != wanted_platform:
                continue
            game_id = row.get("id")
            title = row.get("title")
            if game_id is None or not title:
                continue
            out.append(
                GameSearchResult(
                    provider_name=self.name,
                    provider_game_id=str(game_id),
                    title=title,
                    confidence=1.0 if title.casefold() == normalized else 0.7,
                )
            )
        return out

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        for row in self._cache.values():
            if str(row.get("id")) == str(provider_game_id):
                return self._row_to_meta(provider_game_id, row)
        raise NotFoundError(
            f"LaunchBox cache has no game with id={provider_game_id}"
        )

    def _row_to_meta(
        self, provider_game_id: str, row: dict[str, Any]
    ) -> GameMetadata:
        fields: dict[ProviderField, Any] = {}
        if title := row.get("title"):
            fields[ProviderField.TITLE] = title
        if summary := row.get("summary"):
            fields[ProviderField.SUMMARY] = summary
        if developer := row.get("developer"):
            fields[ProviderField.DEVELOPER] = developer
        if publisher := row.get("publisher"):
            fields[ProviderField.PUBLISHER] = publisher
        if genres := row.get("genres"):
            fields[ProviderField.GENRES] = list(genres)
        if year := row.get("year"):
            with contextlib.suppress(TypeError, ValueError):
                fields[ProviderField.RELEASE_DATE] = datetime(
                    int(year), 1, 1, tzinfo=UTC
                )
        cover_url = row.get("cover_url")
        if cover_url:
            fields[ProviderField.COVER] = cover_url

        return GameMetadata(
            provider_name=self.name,
            provider_game_id=str(provider_game_id),
            fields=fields,
            cover_url=cover_url,
            fetched_at=datetime.now(UTC),
        )

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        # LaunchBox cover URLs in the cache point to LB's CDN; we don't
        # implement the cover fetch in this slice — the bulk importer
        # in v1 will stamp local paths into the cache and that path
        # becomes the canonical source.
        raise NotImplementedError(
            "LaunchBox cover fetch lands with the v1 bulk importer."
        )

    def get_platform_mapping(self, platform_slug: str) -> str | None:
        return self._platform_mapping.get(platform_slug)


register_provider("launchbox", LaunchBoxProvider)
