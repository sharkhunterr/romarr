"""GET /api/v3/game/lookup tests (slice 144).

The endpoint aggregates `search_games` across every enabled
provider. We monkeypatch :func:`load_enabled_providers` to
return a small set of fake providers so the test stays
hermetic — the real provider HTTP paths are exercised by
their own provider unit tests.
"""

from __future__ import annotations

from collections.abc import Iterable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password
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
    assert len(body) == 4
    # Confidence-descending order across providers.
    confidences = [row["confidence"] for row in body]
    assert confidences == sorted(confidences, reverse=True)
    # Rank is the row index in the response.
    ranks = [row["rank"] for row in body]
    assert ranks == [0, 1, 2, 3]


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
