"""ScreenScraper provider tests (T028, T029)."""

from __future__ import annotations

import httpx
import pytest
import respx

from romarr.metadata import PROVIDER_REGISTRY, ProviderField
from romarr.metadata.errors import AuthError, NotFoundError
from romarr.metadata.providers.screenscraper import (
    ScreenScraperProvider,
    _parse_players,
    _pick_earliest_release,
    _pick_genres,
    _pick_localized,
    _pick_title,
)


@pytest.fixture
def ss_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0))


def _make_provider(client: httpx.AsyncClient) -> ScreenScraperProvider:
    p = ScreenScraperProvider(rate_limit_rps=100, rate_limit_burst=100, client=client)
    p.configure(
        {
            "devid": "dev-1",
            "devpassword": "dev-pwd",
            "ssid": "alice",
            "sspassword": "user-pwd",
        }
    )
    return p


# ---------------------------------------------------------------------------
# T029 — auth via URL params
# ---------------------------------------------------------------------------


async def test_search_carries_dev_and_user_credentials_as_url_params(
    ss_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ss_client)
    captured: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200, json={"response": {"jeux": []}}
        )

    with respx.mock:
        respx.get(
            "https://api.screenscraper.fr/api2/jeuRecherche.php"
        ).mock(side_effect=_record)
        await p.search_games("Sonic", platform_slug="genesis")

    assert captured, "jeuRecherche.php was not called"
    request = captured[-1]
    params = dict(request.url.params)
    assert params["devid"] == "dev-1"
    assert params["devpassword"] == "dev-pwd"
    assert params["ssid"] == "alice"
    assert params["sspassword"] == "user-pwd"
    assert params["output"] == "json"
    assert params["softname"] == "romarr"
    assert params["systemeid"] == "1"  # genesis → screenscraper id 1


async def test_configure_rejects_partial_credentials(
    ss_client: httpx.AsyncClient,
) -> None:
    p = ScreenScraperProvider(
        rate_limit_rps=100, rate_limit_burst=100, client=ss_client
    )
    with pytest.raises(AuthError):
        p.configure({"devid": "x", "devpassword": "y", "ssid": "z"})


async def test_403_response_maps_to_auth_error(
    ss_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ss_client)
    with respx.mock:
        respx.get(
            "https://api.screenscraper.fr/api2/jeuRecherche.php"
        ).mock(return_value=httpx.Response(403))
        with pytest.raises(AuthError):
            await p.search_games("Sonic")


async def test_423_quota_locked_maps_to_auth_error(
    ss_client: httpx.AsyncClient,
) -> None:
    """ScreenScraper returns 423 when the user's daily quota is exhausted."""
    p = _make_provider(ss_client)
    with respx.mock:
        respx.get(
            "https://api.screenscraper.fr/api2/jeuRecherche.php"
        ).mock(return_value=httpx.Response(423))
        with pytest.raises(AuthError):
            await p.search_games("Sonic")


# ---------------------------------------------------------------------------
# T028 — get_game returns parsed GameMetadata
# ---------------------------------------------------------------------------


async def test_get_game_populates_documented_fields(
    ss_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ss_client)

    payload = {
        "response": {
            "jeu": {
                "id": 1234,
                "noms": [
                    {"region": "us", "text": "Sonic the Hedgehog"},
                    {"region": "jp", "text": "ソニック・ザ・ヘッジホッグ"},
                ],
                "synopsis": [
                    {"langue": "en", "text": "Genesis classic."},
                    {"langue": "fr", "text": "Le classique de la Megadrive."},
                ],
                "genres": [
                    {
                        "noms": [
                            {"langue": "en", "text": "Platform"},
                            {"langue": "fr", "text": "Plates-formes"},
                        ]
                    },
                    {
                        "noms": [
                            {"langue": "en", "text": "Action"},
                            {"langue": "fr", "text": "Action"},
                        ]
                    },
                ],
                "joueurs": "1-2",
                "dates": [
                    {"region": "us", "text": "1991-06-23"},
                    {"region": "eu", "text": "1991-11-21"},
                ],
                "medias": [
                    {
                        "type": "box-2D",
                        "url": "https://www.screenscraper.fr/cover.png",
                    }
                ],
            }
        }
    }

    with respx.mock:
        respx.get("https://api.screenscraper.fr/api2/jeuInfos.php").mock(
            return_value=httpx.Response(200, json=payload)
        )
        meta = await p.get_game("1234")

    assert meta.fields[ProviderField.TITLE] == "Sonic the Hedgehog"
    assert meta.fields[ProviderField.SUMMARY] == "Genesis classic."
    assert meta.fields[ProviderField.GENRES] == ["Platform", "Action"]
    assert meta.fields[ProviderField.RELEASE_DATE].year == 1991
    assert meta.fields[ProviderField.RELEASE_DATE].month == 6
    assert meta.fields[ProviderField.PLAYERS_MIN] == 1
    assert meta.fields[ProviderField.PLAYERS_MAX] == 2
    assert (
        meta.fields[ProviderField.COVER]
        == "https://www.screenscraper.fr/cover.png"
    )
    assert meta.cover_url == meta.fields[ProviderField.COVER]


async def test_get_game_unknown_id_raises_not_found(
    ss_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(ss_client)
    with respx.mock:
        respx.get("https://api.screenscraper.fr/api2/jeuInfos.php").mock(
            return_value=httpx.Response(200, json={"response": {}})
        )
        with pytest.raises(NotFoundError):
            await p.get_game("999")


# ---------------------------------------------------------------------------
# Parsing helpers — direct unit tests
# ---------------------------------------------------------------------------


def test_pick_title_prefers_us_then_world() -> None:
    noms = [
        {"region": "jp", "text": "JP"},
        {"region": "wor", "text": "WORLD"},
        {"region": "us", "text": "US"},
    ]
    assert _pick_title(noms, "en") == "US"


def test_pick_title_falls_back_when_no_preferred_region() -> None:
    noms = [
        {"region": "kr", "text": "Korean Title"},
        {"region": "fr", "text": "French Title"},
    ]
    assert _pick_title(noms, "en") == "Korean Title"


def test_pick_localized_picks_matching_language() -> None:
    rows = [
        {"langue": "fr", "text": "FR"},
        {"langue": "en", "text": "EN"},
    ]
    assert _pick_localized(rows, "en") == "EN"
    assert _pick_localized(rows, "fr") == "FR"


def test_pick_genres_dedupes() -> None:
    genres = [
        {"noms": [{"langue": "en", "text": "Action"}]},
        {"noms": [{"langue": "en", "text": "Action"}]},
        {"noms": [{"langue": "en", "text": "Adventure"}]},
    ]
    assert _pick_genres(genres, "en") == ["Action", "Adventure"]


def test_pick_earliest_release_picks_minimum() -> None:
    rows = [
        {"region": "eu", "text": "1992-01-01"},
        {"region": "us", "text": "1991-06-23"},
        {"region": "jp", "text": "1991-07-26"},
    ]
    earliest = _pick_earliest_release(rows)
    assert earliest is not None
    assert earliest.year == 1991 and earliest.month == 6


def test_parse_players_range_and_single() -> None:
    assert _parse_players("1-4") == (1, 4)
    assert _parse_players("2") == (2, 2)
    assert _parse_players("1+") == (1, 1)
    assert _parse_players("") == (None, None)
    assert _parse_players("garbage") == (None, None)


# ---------------------------------------------------------------------------
# Self-registration + platform mapping
# ---------------------------------------------------------------------------


def test_self_registered() -> None:
    assert PROVIDER_REGISTRY.get("screenscraper") is ScreenScraperProvider


def test_platform_mapping_genesis_is_1(ss_client: httpx.AsyncClient) -> None:
    # Slice 411 widened the default mapping to cover disc-based
    # platforms (psx / ps2 / ngc / dc / saturn) so the user
    # doesn't have to wire them by hand.
    p = ScreenScraperProvider(rate_limit_rps=100, rate_limit_burst=100, client=ss_client)
    assert p.get_platform_mapping("genesis") == 1
    assert p.get_platform_mapping("psx") == 57
    assert p.get_platform_mapping("unknown-slug") is None
