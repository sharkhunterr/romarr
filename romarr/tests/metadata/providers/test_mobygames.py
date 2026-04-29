"""MobyGames provider tests (T031, T032)."""

from __future__ import annotations

import httpx
import pytest
import respx

from romarr.metadata import PROVIDER_REGISTRY, ProviderField
from romarr.metadata.errors import AuthError, NotFoundError
from romarr.metadata.providers.mobygames import (
    MobyGamesProvider,
    _parse_player_range,
    _pick_release_metadata,
)


@pytest.fixture
def mg_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0))


def _make_provider(client: httpx.AsyncClient) -> MobyGamesProvider:
    p = MobyGamesProvider(rate_limit_rps=100, rate_limit_burst=100, client=client)
    p.configure({"api_key": "mg-key"})
    return p


# ---------------------------------------------------------------------------
# T031 — auth + 403 mapping
# ---------------------------------------------------------------------------


async def test_search_carries_api_key_query_param(
    mg_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(mg_client)
    captured: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"games": []})

    with respx.mock:
        respx.get("https://api.mobygames.com/v1/games").mock(side_effect=_record)
        await p.search_games("Sonic", platform_slug="megadrive")

    assert captured
    params = dict(captured[-1].url.params)
    assert params["api_key"] == "mg-key"
    assert params["title"] == "Sonic"
    assert params["platform"] == "16"  # mobygames id for megadrive


async def test_403_response_maps_to_auth_error(
    mg_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(mg_client)
    with respx.mock:
        respx.get("https://api.mobygames.com/v1/games").mock(
            return_value=httpx.Response(403)
        )
        with pytest.raises(AuthError):
            await p.search_games("Sonic")


async def test_configure_rejects_missing_api_key(
    mg_client: httpx.AsyncClient,
) -> None:
    p = MobyGamesProvider(rate_limit_rps=100, rate_limit_burst=100, client=mg_client)
    with pytest.raises(AuthError):
        p.configure({})


# ---------------------------------------------------------------------------
# T032 — get_game returns parsed GameMetadata
# ---------------------------------------------------------------------------


async def test_get_game_populates_documented_fields(
    mg_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(mg_client)

    payload = {
        "game_id": 1234,
        "title": "Sonic the Hedgehog",
        "description": "Genesis classic.",
        "genres": [
            {"genre_category": "Basic Genres", "genre_name": "Action"},
            {"genre_category": "Sub-Genre", "genre_name": "Platform"},
            {"genre_category": "Perspective", "genre_name": "Side view"},
        ],
        "platforms": [
            {
                "platform_id": 16,
                "platform_name": "Genesis",
                "first_release_date": "1991-06-23",
                "releases": [
                    {
                        "companies": [
                            {"role": "Developed by", "company_name": "Sonic Team"},
                            {"role": "Published by", "company_name": "Sega"},
                        ]
                    }
                ],
                "attributes": [
                    {
                        "attribute_category_name": "Number of Players",
                        "attribute_name": "1-2 Players",
                    }
                ],
            }
        ],
        "ratings": [
            {"rating_system_name": "ESRB Rating", "rating_name": "Everyone"}
        ],
        "sample_cover": {"image": "https://www.mobygames.com/covers/1234.jpg"},
    }

    with respx.mock:
        respx.get("https://api.mobygames.com/v1/games/1234").mock(
            return_value=httpx.Response(200, json=payload)
        )
        meta = await p.get_game("1234")

    assert meta.fields[ProviderField.TITLE] == "Sonic the Hedgehog"
    assert meta.fields[ProviderField.SUMMARY] == "Genesis classic."
    # Only "Basic Genres" + "Sub-Genre" categories are kept; "Perspective" is dropped.
    assert meta.fields[ProviderField.GENRES] == ["Action", "Platform"]
    assert meta.fields[ProviderField.RELEASE_DATE].year == 1991
    assert meta.fields[ProviderField.DEVELOPER] == "Sonic Team"
    assert meta.fields[ProviderField.PUBLISHER] == "Sega"
    assert meta.fields[ProviderField.AGE_RATING] == "ESRB Everyone"
    assert (
        meta.fields[ProviderField.COVER]
        == "https://www.mobygames.com/covers/1234.jpg"
    )
    assert meta.fields[ProviderField.PLAYERS_MIN] == 1
    assert meta.fields[ProviderField.PLAYERS_MAX] == 2


async def test_get_game_unknown_id_raises_not_found(
    mg_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(mg_client)
    with respx.mock:
        respx.get("https://api.mobygames.com/v1/games/9999").mock(
            return_value=httpx.Response(200, json={})
        )
        with pytest.raises(NotFoundError):
            await p.get_game("9999")


async def test_search_returns_results(
    mg_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(mg_client)
    payload = {
        "games": [
            {"game_id": 1, "title": "Sonic the Hedgehog"},
            {"game_id": 2, "title": "Sonic 2"},
        ]
    }
    with respx.mock:
        respx.get("https://api.mobygames.com/v1/games").mock(
            return_value=httpx.Response(200, json=payload)
        )
        results = await p.search_games("Sonic", platform_slug="megadrive")
    titles = [r.title for r in results]
    assert titles == ["Sonic the Hedgehog", "Sonic 2"]


# ---------------------------------------------------------------------------
# Parsing helpers — direct unit tests
# ---------------------------------------------------------------------------


def test_parse_player_range_variants() -> None:
    assert _parse_player_range("1-4 Players") == (1, 4)
    assert _parse_player_range("2 Players") == (2, 2)
    assert _parse_player_range("Single player") == (None, None)


def test_pick_release_metadata_picks_earliest_and_majority() -> None:
    platforms = [
        {
            "first_release_date": "1991-11-21",
            "releases": [
                {
                    "companies": [
                        {"role": "Developed by", "company_name": "Sonic Team"},
                        {"role": "Published by", "company_name": "Sega Europe"},
                    ]
                }
            ],
        },
        {
            "first_release_date": "1991-06-23",
            "releases": [
                {
                    "companies": [
                        {"role": "Developed by", "company_name": "Sonic Team"},
                        {"role": "Published by", "company_name": "Sega"},
                    ]
                }
            ],
        },
    ]
    earliest, dev, pub = _pick_release_metadata(platforms)
    assert earliest is not None and earliest.month == 6
    assert dev == "Sonic Team"
    # Both Sega rows count once each; tie broken by max() determinism.
    assert pub in {"Sega", "Sega Europe"}


# ---------------------------------------------------------------------------
# Self-registration + platform mapping
# ---------------------------------------------------------------------------


def test_self_registered() -> None:
    assert PROVIDER_REGISTRY.get("mobygames") is MobyGamesProvider


def test_platform_mapping_megadrive_is_16(mg_client: httpx.AsyncClient) -> None:
    p = MobyGamesProvider(rate_limit_rps=100, rate_limit_burst=100, client=mg_client)
    assert p.get_platform_mapping("megadrive") == 16
    assert p.get_platform_mapping("psx") is None
