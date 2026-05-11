"""RetroAchievements provider tests (T040).

Enrichment-only — the GameMetadata returned by ``get_game`` MUST
contain only ``ACHIEVEMENTS_COUNT`` (FR-006); never ``TITLE``,
``SUMMARY``, or any other matching-grade field.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from romarr.metadata import PROVIDER_REGISTRY, ProviderField
from romarr.metadata.errors import AuthError, NotFoundError
from romarr.metadata.providers.retroachievements import RetroAchievementsProvider


@pytest.fixture
def ra_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0))


def _make_provider(client: httpx.AsyncClient) -> RetroAchievementsProvider:
    p = RetroAchievementsProvider(
        rate_limit_rps=100, rate_limit_burst=100, client=client
    )
    p.configure({"username": "alice", "api_key": "ra-key"})
    return p


async def test_get_game_populates_only_achievements_count(
    ra_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ra_client)

    payload = {
        "ID": 1234,
        "Title": "Sonic the Hedgehog",
        "ConsoleID": 1,
        "NumAchievements": 42,
    }
    with respx.mock:
        respx.get("https://retroachievements.org/API/API_GetGame.php").mock(
            return_value=httpx.Response(200, json=payload)
        )
        meta = await p.get_game("1234")

    # FR-006: ONLY achievements_count is contributed.
    assert set(meta.fields.keys()) == {ProviderField.ACHIEVEMENTS_COUNT}
    assert meta.fields[ProviderField.ACHIEVEMENTS_COUNT] == 42
    assert meta.cover_url is None


async def test_get_game_no_achievements_returns_empty_fields(
    ra_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ra_client)

    with respx.mock:
        respx.get("https://retroachievements.org/API/API_GetGame.php").mock(
            return_value=httpx.Response(
                200,
                json={"ID": 1, "Title": "Some Game", "NumAchievements": 0},
            )
        )
        meta = await p.get_game("1")

    assert meta.fields == {}


async def test_get_game_unknown_id_raises_not_found(
    ra_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ra_client)
    with respx.mock:
        respx.get("https://retroachievements.org/API/API_GetGame.php").mock(
            return_value=httpx.Response(200, json={})
        )
        with pytest.raises(NotFoundError):
            await p.get_game("999")


async def test_search_games_filters_by_console(
    ra_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ra_client)

    payload = [
        {"ID": 1, "Title": "Sonic the Hedgehog"},
        {"ID": 2, "Title": "Sonic 2"},
        {"ID": 3, "Title": "Mario Bros."},
    ]
    with respx.mock:
        respx.get("https://retroachievements.org/API/API_GetGameList.php").mock(
            return_value=httpx.Response(200, json=payload)
        )
        results = await p.search_games("Sonic", platform_slug="genesis")

    titles = {r.title for r in results}
    assert titles == {"Sonic the Hedgehog", "Sonic 2"}


async def test_search_games_without_platform_returns_empty(
    ra_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ra_client)
    # No platform_slug → RA can't disambiguate, returns nothing.
    results = await p.search_games("Sonic")
    assert results == []


async def test_get_cover_raises_not_implemented(
    ra_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ra_client)
    with pytest.raises(NotImplementedError):
        await p.get_cover("1")


async def test_configure_rejects_missing_creds(
    ra_client: httpx.AsyncClient,
) -> None:
    p = RetroAchievementsProvider(
        rate_limit_rps=100, rate_limit_burst=100, client=ra_client
    )
    with pytest.raises(AuthError):
        p.configure({"username": "alice"})  # missing api_key


def test_self_registered() -> None:
    assert (
        PROVIDER_REGISTRY.get("retroachievements") is RetroAchievementsProvider
    )


def test_capabilities_only_achievements_count() -> None:
    cap = RetroAchievementsProvider.capabilities
    assert cap.contributable_fields == frozenset(
        {ProviderField.ACHIEVEMENTS_COUNT}
    )
    assert cap.invoked_in_scan is True


def test_platform_mapping_genesis_is_1() -> None:
    p = RetroAchievementsProvider(
        rate_limit_rps=100,
        rate_limit_burst=100,
        client=httpx.AsyncClient(),
    )
    # Slice 411 widened the default mapping to cover most major
    # consoles including disc-based ones.
    assert p.get_platform_mapping("genesis") == 1
    assert p.get_platform_mapping("psx") == 12
    assert p.get_platform_mapping("unknown-slug") is None
