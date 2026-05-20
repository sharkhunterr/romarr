"""GET /api/v3/game/lookup + POST /api/v3/game/lookup/add tests
(slices 144 + 145).

The endpoints aggregate `search_games` across every enabled
provider and instantiate a Game from a chosen candidate. We
monkeypatch :func:`load_enabled_providers` to return a small
set of fake providers so the test stays hermetic — the real
provider HTTP paths are exercised by their own provider unit
tests.
"""

from __future__ import annotations

from collections.abc import Iterable

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password
from romarr.domain.models import Game, Platform
from romarr.metadata.api.lookup import slugify_title
from romarr.metadata.providers import MetadataProvider
from romarr.metadata.providers.base import ProviderCapabilities
from romarr.metadata.types import GameMetadata, GameSearchResult


async def _seed_admin_and_login(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="admin",
                role=ROLE_ADMIN,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert response.status_code == 204


class _FakeProvider(MetadataProvider):
    """Minimal provider stub for the lookup tests.

    Returns whatever the test fixture hands it; never hits the
    network. Implements just enough of the abstract API to
    satisfy MetadataProvider's ABC.
    """

    name = "fake"
    capabilities = ProviderCapabilities(
        name="fake",
        requires_auth=False,
        contributable_fields=frozenset(),
        invoked_in_scan=True,
    )

    def __init__(
        self, *, name: str, results: Iterable[GameSearchResult]
    ) -> None:
        super().__init__(rate_limit_rps=10, rate_limit_burst=20)
        self.name = name
        self._results = list(results)

    def configure(self, config: dict) -> None:  # noqa: ARG002
        return None

    async def health_check(self) -> bool:
        return True

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:  # noqa: ARG002
        # Echo whatever was seeded; the test shapes the candidate
        # set up front so assertion logic stays explicit.
        return list(self._results)

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        raise NotImplementedError

    async def get_cover(
        self, provider_game_id: str
    ) -> tuple[bytes, str]:
        raise NotImplementedError

    def get_platform_mapping(
        self, platform_slug: str
    ) -> int | str | None:  # noqa: ARG002
        return None


def _make_results(
    *, provider: str, count: int, base_confidence: float
) -> list[GameSearchResult]:
    return [
        GameSearchResult(
            provider_name=provider,
            provider_game_id=f"{provider}-{i}",
            title=f"Sonic {i + 1}",
            confidence=base_confidence - i * 0.1,
        )
        for i in range(count)
    ]


@pytest.fixture
def patched_lookup(monkeypatch: pytest.MonkeyPatch):
    """Replace `load_enabled_providers` with a callable the test
    hands a list of fake providers."""

    def _install(providers: list[MetadataProvider]) -> None:
        async def _fake(_session, *, scan: bool = True):  # noqa: ARG001
            return providers

        monkeypatch.setattr(
            "romarr.metadata.api.lookup.load_enabled_providers",
            _fake,
        )

    return _install


@pytest.mark.asyncio
async def test_lookup_merges_and_ranks_by_confidence(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    patched_lookup,
) -> None:
    """Two providers each return two results; the merged response
    ranks every row globally by confidence descending."""
    await _seed_admin_and_login(api_engine, api_client)
    patched_lookup(
        [
            _FakeProvider(
                name="igdb",
                results=_make_results(
                    provider="igdb", count=2, base_confidence=0.95
                ),
            ),
            _FakeProvider(
                name="screenscraper",
                results=_make_results(
                    provider="screenscraper",
                    count=2,
                    base_confidence=0.80,
                ),
            ),
        ]
    )

    resp = await api_client.get("/api/v3/game/lookup?q=sonic")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    # Slice 410 — the two fake providers both return "Sonic 1"
    # and "Sonic 2"; cross-provider dedupe collapses to 2 rows,
    # each tagged with both provider hits.
    assert len(body) == 2
    confidences = [row["confidence"] for row in body]
    assert confidences == sorted(confidences, reverse=True)
    ranks = [row["rank"] for row in body]
    assert ranks == [0, 1]
    # Every row carries both providers (igdb + screenscraper).
    for row in body:
        names = sorted(p["name"] for p in row["providers"])
        assert names == ["igdb", "screenscraper"]


@pytest.mark.asyncio
async def test_lookup_ignores_provider_failures(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    patched_lookup,
) -> None:
    """A single provider raising on search_games doesn't sink the
    whole lookup — partial results from healthy providers come back."""
    await _seed_admin_and_login(api_engine, api_client)

    class _FailingProvider(_FakeProvider):
        async def search_games(
            self, query: str, *, platform_slug: str | None = None
        ) -> list[GameSearchResult]:
            raise RuntimeError("network blew up")

    patched_lookup(
        [
            _FailingProvider(name="broken", results=[]),
            _FakeProvider(
                name="ok",
                results=_make_results(
                    provider="ok", count=1, base_confidence=0.5
                ),
            ),
        ]
    )

    resp = await api_client.get("/api/v3/game/lookup?q=sonic")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["providerName"] == "ok"


@pytest.mark.asyncio
async def test_lookup_requires_query(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    resp = await api_client.get("/api/v3/game/lookup?q=")
    # FastAPI rejects empty `q` because `min_length=1`.
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_lookup_requires_admin(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/game/lookup?q=sonic")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_lookup_limit_truncates_results(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    patched_lookup,
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    patched_lookup(
        [
            _FakeProvider(
                name="igdb",
                results=_make_results(
                    provider="igdb", count=10, base_confidence=0.9
                ),
            ),
        ]
    )
    resp = await api_client.get("/api/v3/game/lookup?q=sonic&limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# slugify_title — pure helper unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Sonic the Hedgehog", "sonic-the-hedgehog"),
        ("Pokémon Red", "pokemon-red"),
        ("Final Fantasy VII", "final-fantasy-vii"),
        ("  Sonic   2  ", "sonic-2"),
        ("Zelda: Ocarina of Time", "zelda-ocarina-of-time"),
        ("!!!", "untitled"),
        ("", "untitled"),
    ],
)
def test_slugify_title(title: str, expected: str) -> None:
    assert slugify_title(title) == expected


# ---------------------------------------------------------------------------
# POST /api/v3/game/lookup/add
# ---------------------------------------------------------------------------


async def _seed_platform(
    api_engine: AsyncEngine, *, slug: str = "megadrive"
) -> int:
    """Seed a Platform row and return its id."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(slug=slug, name=slug.upper())
        session.add(platform)
        await session.commit()
        await session.refresh(platform)
        return platform.id


@pytest.mark.asyncio
async def test_lookup_add_creates_game_with_provider_fk(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The happy path persists a Game on the chosen platform with
    the provider id stored in the matching FK column and
    ``needs_metadata_refresh`` set so the aggregator picks it up."""
    await _seed_admin_and_login(api_engine, api_client)
    platform_id = await _seed_platform(api_engine)

    resp = await api_client.post(
        "/api/v3/game/lookup/add",
        json={
            "providerName": "igdb",
            "providerGameId": "1234",
            "title": "Sonic the Hedgehog",
            "platformId": platform_id,
            "monitored": True,
        },
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["title"] == "Sonic the Hedgehog"
    assert body["slug"] == "sonic-the-hedgehog"
    assert body["platform_id"] == platform_id
    assert body["igdb_id"] == 1234
    assert body["monitored"] is True
    assert body["needs_metadata_refresh"] is True
    # The auxiliary FK columns stay null — only one provider gets
    # written per add.
    assert body["mobygames_id"] is None
    assert body["screenscraper_id"] is None


@pytest.mark.asyncio
async def test_lookup_add_disambiguates_slug_collision(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Two adds of the same title on the same platform produce
    distinct slugs (``-2`` suffix) so the unique constraint
    holds."""
    await _seed_admin_and_login(api_engine, api_client)
    platform_id = await _seed_platform(api_engine)

    payload = {
        "providerName": "igdb",
        "providerGameId": "1",
        "title": "Sonic",
        "platformId": platform_id,
    }
    first = await api_client.post("/api/v3/game/lookup/add", json=payload)
    assert first.status_code == 201
    assert first.json()["slug"] == "sonic"

    second_payload = dict(payload, providerGameId="2")
    second = await api_client.post(
        "/api/v3/game/lookup/add", json=second_payload
    )
    assert second.status_code == 201
    assert second.json()["slug"] == "sonic-2"


@pytest.mark.asyncio
async def test_lookup_add_rejects_unknown_platform(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)

    resp = await api_client.post(
        "/api/v3/game/lookup/add",
        json={
            "providerName": "igdb",
            "providerGameId": "1",
            "title": "Sonic",
            "platformId": 99999,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "platform_not_found"


@pytest.mark.asyncio
async def test_lookup_add_rejects_auxiliary_provider(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Auxiliary providers (covers, hashes, durations) don't have
    a Game FK column — adding via them is a contract violation."""
    await _seed_admin_and_login(api_engine, api_client)
    platform_id = await _seed_platform(api_engine)

    resp = await api_client.post(
        "/api/v3/game/lookup/add",
        json={
            "providerName": "steamgriddb",
            "providerGameId": "1",
            "title": "Sonic",
            "platformId": platform_id,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "unsupported_provider"


async def _seed_library_with_profiles(
    api_engine: AsyncEngine, *, name: str = "Cartridges"
) -> int:
    """Seed a Library with the five required profile FKs so the
    lookup/add tests can verify the library_id round-trip
    (slice 385). The profile values themselves don't matter — the
    endpoint only stamps Game.library_id and lets the importer
    consume the cascade later."""
    from romarr.libraries.models import Library
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        QualityProfile,
        RegionProfile,
    )

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        quality = QualityProfile(
            name=f"quality-{name}",
            allowed_formats=["raw", "zip"],
            preferred_format="raw",
            upgrade_until_format="raw",
        )
        region = RegionProfile(
            name=f"region-{name}",
            priorities=["USA"],
            allow_fallback_outside_priorities=True,
            exclude_regions=[],
        )
        dump = DumpProfile(
            name=f"dump-{name}",
            allowed_dump_status=["verified"],
            allow_proto_beta=False,
            allow_hacks=False,
            allow_trainers=False,
            allow_translations=False,
            prefer_revision="latest",
        )
        language = LanguageProfile(
            name=f"language-{name}",
            required_languages=[],
            preferred_languages=["en"],
            exclude_japanese_only=False,
        )
        naming = NamingProfile(
            name=f"naming-{name}",
            convention="romm",
            template="{{ game.title }}",
        )
        session.add_all([quality, region, dump, language, naming])
        await session.commit()
        for p in (quality, region, dump, language, naming):
            await session.refresh(p)

        library = Library(
            name=name,
            path=f"/tmp/{name}",
            quality_profile_id=quality.id,
            region_profile_id=region.id,
            dump_profile_id=dump.id,
            language_profile_id=language.id,
            naming_profile_id=naming.id,
        )
        session.add(library)
        await session.commit()
        await session.refresh(library)
        return library.id


@pytest.mark.asyncio
async def test_lookup_add_persists_library_id(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Slice 385 — operator's library pick from the AddGame
    modal lands on Game.library_id so the importer routes the
    eventual download to the right root + profile cascade."""
    await _seed_admin_and_login(api_engine, api_client)
    platform_id = await _seed_platform(api_engine)
    library_id = await _seed_library_with_profiles(api_engine)

    resp = await api_client.post(
        "/api/v3/game/lookup/add",
        json={
            "providerName": "igdb",
            "providerGameId": "42",
            "title": "Sonic with library",
            "platformId": platform_id,
            "libraryId": library_id,
        },
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["library_id"] == library_id


@pytest.mark.asyncio
async def test_lookup_add_rejects_unknown_library(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """An invalid libraryId surfaces 404 with errorCode
    ``library_not_found`` rather than letting the FK fail at
    flush time with a 500."""
    await _seed_admin_and_login(api_engine, api_client)
    platform_id = await _seed_platform(api_engine)

    resp = await api_client.post(
        "/api/v3/game/lookup/add",
        json={
            "providerName": "igdb",
            "providerGameId": "1",
            "title": "Sonic",
            "platformId": platform_id,
            "libraryId": 99999,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "library_not_found"


@pytest.mark.asyncio
async def test_lookup_add_rejects_non_integer_provider_id(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    platform_id = await _seed_platform(api_engine)

    resp = await api_client.post(
        "/api/v3/game/lookup/add",
        json={
            "providerName": "igdb",
            "providerGameId": "abc-not-a-number",
            "title": "Sonic",
            "platformId": platform_id,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "invalid_provider_game_id"


@pytest.mark.asyncio
async def test_lookup_add_requires_admin(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v3/game/lookup/add",
        json={
            "providerName": "igdb",
            "providerGameId": "1",
            "title": "Sonic",
            "platformId": 1,
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_lookup_add_persists_in_database(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """End-to-end check: the row created by the endpoint is
    actually queryable from a fresh session, so the commit really
    happened."""
    await _seed_admin_and_login(api_engine, api_client)
    platform_id = await _seed_platform(api_engine)

    resp = await api_client.post(
        "/api/v3/game/lookup/add",
        json={
            "providerName": "screenscraper",
            "providerGameId": "42",
            "title": "Pokémon Red",
            "platformId": platform_id,
            "monitored": False,
        },
    )
    assert resp.status_code == 201
    new_id = resp.json()["id"]

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = (
            await session.execute(select(Game).where(Game.id == new_id))
        ).scalar_one()
        assert row.title == "Pokémon Red"
        assert row.slug == "pokemon-red"
        assert row.screenscraper_id == 42
        assert row.igdb_id is None
        assert row.monitored is False
        assert row.needs_metadata_refresh is True


# ---------------------------------------------------------------------------
# Integration endpoints — IGDB-native surface for external request
# managers (allseerr). /integrations/request + /integrations/status.
# ---------------------------------------------------------------------------


async def _seed_platform_with_igdb(
    api_engine: AsyncEngine, *, slug: str = "gba", igdb_id: int = 24
) -> int:
    """Seed a Platform carrying an ``igdb_id`` and return its row id."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(slug=slug, name=slug.upper(), igdb_id=igdb_id)
        session.add(platform)
        await session.commit()
        await session.refresh(platform)
        return platform.id


@pytest.mark.asyncio
async def test_integration_request_adds_game(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """POST /integrations/request resolves the IGDB platform id to a
    Romarr platform and adds the game."""
    await _seed_admin_and_login(api_engine, api_client)
    platform_id = await _seed_platform_with_igdb(api_engine, igdb_id=24)

    resp = await api_client.post(
        "/api/v3/game/integrations/request",
        json={
            "igdbId": 7346,
            "igdbPlatformId": 24,
            "title": "The Legend of Zelda: The Minish Cap",
        },
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["status"] == "added"
    assert body["game"]["igdb_id"] == 7346
    assert body["game"]["platform_id"] == platform_id
    assert body["game"]["monitored"] is True


@pytest.mark.asyncio
async def test_integration_request_is_idempotent(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A second request for the same IGDB game on the same platform
    returns the existing row with status=already_present."""
    await _seed_admin_and_login(api_engine, api_client)
    await _seed_platform_with_igdb(api_engine, igdb_id=24)

    payload = {
        "igdbId": 1234,
        "igdbPlatformId": 24,
        "title": "Metroid Fusion",
    }
    first = await api_client.post(
        "/api/v3/game/integrations/request", json=payload
    )
    assert first.status_code == 200
    assert first.json()["status"] == "added"

    second = await api_client.post(
        "/api/v3/game/integrations/request", json=payload
    )
    assert second.status_code == 200
    assert second.json()["status"] == "already_present"
    assert second.json()["game"]["id"] == first.json()["game"]["id"]


@pytest.mark.asyncio
async def test_integration_request_unknown_platform(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """An IGDB platform id with no Romarr mapping → 404."""
    await _seed_admin_and_login(api_engine, api_client)

    resp = await api_client.post(
        "/api/v3/game/integrations/request",
        json={
            "igdbId": 99,
            "igdbPlatformId": 999999,
            "title": "Unknown Platform Game",
        },
    )
    assert resp.status_code == 404
    # romarr's error handler flattens HTTPException(detail=dict) to a
    # top-level {errorMessage, errorCode} envelope.
    assert resp.json()["errorCode"] == "platform_not_supported"


@pytest.mark.asyncio
async def test_integration_status_reports_presence(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """GET /integrations/status flips to present=true once the game
    is in the library."""
    await _seed_admin_and_login(api_engine, api_client)
    await _seed_platform_with_igdb(api_engine, igdb_id=24)

    before = await api_client.get(
        "/api/v3/game/integrations/status?igdbId=4242"
    )
    assert before.status_code == 200
    assert before.json()["present"] is False

    await api_client.post(
        "/api/v3/game/integrations/request",
        json={
            "igdbId": 4242,
            "igdbPlatformId": 24,
            "title": "Golden Sun",
        },
    )

    after = await api_client.get(
        "/api/v3/game/integrations/status?igdbId=4242"
    )
    assert after.status_code == 200
    assert after.json()["present"] is True
    assert len(after.json()["games"]) == 1
