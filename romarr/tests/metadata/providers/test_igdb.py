"""IGDB provider tests (T024, T025, T026).

respx-mocked Twitch OAuth + IGDB v4 endpoints. The IGDB client is
exercised against a custom :class:`httpx.AsyncClient` whose transport
is a respx mock — this avoids relying on a global httpx mock and
keeps the bearer-cache / 401-retry behaviour deterministic.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from romarr.metadata import GameMetadata, ProviderField
from romarr.metadata.errors import AuthError, NotFoundError
from romarr.metadata.providers.igdb import IGDBProvider


def _make_provider(
    *,
    client: httpx.AsyncClient,
    clock: list[float] | None = None,
) -> IGDBProvider:
    """Construct an IGDB provider with high rate limits + injected client.

    The clock list lets tests advance "monotonic time" without touching
    real wall clock — useful for the bearer-expiry assertions.
    """
    if clock is None:
        clock = [0.0]
    return IGDBProvider(
        rate_limit_rps=1000,
        rate_limit_burst=1000,
        client=client,
        clock=lambda: clock[0],
    )


@pytest.fixture
def igdb_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0))


@pytest.fixture
def oauth_response() -> dict[str, Any]:
    return {"access_token": "twitch-bearer-1", "expires_in": 3600}


# ---------------------------------------------------------------------------
# T024 — OAuth flow
# ---------------------------------------------------------------------------


async def test_oauth_lazy_fetch_and_cache(
    igdb_client: httpx.AsyncClient, oauth_response: dict[str, Any]
) -> None:
    """First API call triggers OAuth; second call reuses the cached bearer."""
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "id-1", "client_secret": "secret-1"})

    with respx.mock:
        oauth = respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=oauth_response)
        )
        games = respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(200, json=[])
        )

        await provider.search_games("sonic")
        await provider.search_games("mario")

    assert oauth.call_count == 1, "bearer must be cached after first fetch"
    assert games.call_count == 2


async def test_oauth_401_triggers_reauth_and_retry(
    igdb_client: httpx.AsyncClient, oauth_response: dict[str, Any]
) -> None:
    """An in-flight 401 forces ONE re-auth + retry; second 401 bubbles up."""
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "id-1", "client_secret": "secret-1"})

    with respx.mock:
        oauth = respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=oauth_response)
        )
        games = respx.post("https://api.igdb.com/v4/games").mock(
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, json=[]),
            ]
        )
        result = await provider.search_games("sonic")

    assert result == []
    # OAuth fetched once for the initial bearer + once more after the 401.
    assert oauth.call_count == 2
    assert games.call_count == 2


async def test_oauth_refreshes_when_near_expiry(
    igdb_client: httpx.AsyncClient,
) -> None:
    """A bearer within 60 s of expiring is refreshed proactively."""
    clock = [0.0]
    provider = _make_provider(client=igdb_client, clock=clock)
    provider.configure({"client_id": "id-1", "client_secret": "secret-1"})

    with respx.mock:
        oauth = respx.post("https://id.twitch.tv/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json={"access_token": "t1", "expires_in": 100}),
                httpx.Response(200, json={"access_token": "t2", "expires_in": 100}),
            ]
        )
        respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(200, json=[])
        )

        # First call → fetches t1; expires at clock=100.
        await provider.search_games("a")
        assert oauth.call_count == 1

        # Advance to clock=50 — still > 60s before expiry → reuse t1.
        clock[0] = 41.0  # 100 - 41 = 59 < 60 → refresh kicks in
        await provider.search_games("b")
        assert oauth.call_count == 2


async def test_configure_rejects_missing_credentials(
    igdb_client: httpx.AsyncClient,
) -> None:
    provider = _make_provider(client=igdb_client)
    with pytest.raises(AuthError):
        provider.configure({"client_id": "x"})  # missing client_secret


async def test_oauth_401_response_maps_to_auth_error(
    igdb_client: httpx.AsyncClient,
) -> None:
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "bad", "client_secret": "creds"})

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(401)
        )
        with pytest.raises(AuthError):
            await provider.search_games("x")


# ---------------------------------------------------------------------------
# T025 — search + get_game
# ---------------------------------------------------------------------------


async def test_search_games_returns_results(
    igdb_client: httpx.AsyncClient, oauth_response: dict[str, Any]
) -> None:
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "id", "client_secret": "secret"})

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=oauth_response)
        )
        respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": 1234, "name": "Sonic the Hedgehog", "slug": "sonic"},
                    {"id": 1235, "name": "Sonic 2", "slug": "sonic-2"},
                ],
            )
        )
        results = await provider.search_games(
            "Sonic the Hedgehog", platform_slug="genesis"
        )

    assert len(results) == 2
    assert results[0].provider_game_id == "1234"
    assert results[0].title == "Sonic the Hedgehog"
    # Exact case-insensitive match → 0.8 confidence (or 1.0 on case-equal).
    assert results[0].confidence in (0.8, 1.0)


async def test_get_game_populates_documented_fields(
    igdb_client: httpx.AsyncClient, oauth_response: dict[str, Any]
) -> None:
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "id", "client_secret": "secret"})

    igdb_payload = [
        {
            "id": 1234,
            "name": "Sonic the Hedgehog",
            "summary": "Genesis classic.",
            "rating": 87.5,
            "genres": [{"name": "Platform"}, {"name": "Adventure"}],
            "themes": [{"name": "Action"}],
            "franchises": [{"name": "Sonic"}],
            "release_dates": [
                {"date": 677635200},  # 1991-06-23 UTC (Sonic 1 JP launch)
                {"date": 690508800},  # later regional release
            ],
            "involved_companies": [
                {
                    "developer": True,
                    "publisher": False,
                    "company": {"name": "Sonic Team"},
                },
                {
                    "developer": False,
                    "publisher": True,
                    "company": {"name": "Sega"},
                },
            ],
            "age_ratings": [{"rating": 8}],  # PEGI 3
            "cover": {"image_id": "co1234abc"},
        }
    ]

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=oauth_response)
        )
        respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(200, json=igdb_payload)
        )
        meta = await provider.get_game("1234")

    assert isinstance(meta, GameMetadata)
    assert meta.provider_game_id == "1234"
    assert meta.fields[ProviderField.TITLE] == "Sonic the Hedgehog"
    assert meta.fields[ProviderField.SUMMARY] == "Genesis classic."
    assert meta.fields[ProviderField.GENRES] == ["Platform", "Adventure"]
    assert meta.fields[ProviderField.THEMES] == ["Action"]
    assert meta.fields[ProviderField.FRANCHISES] == ["Sonic"]
    assert meta.fields[ProviderField.RATING] == 87.5
    assert meta.fields[ProviderField.DEVELOPER] == "Sonic Team"
    assert meta.fields[ProviderField.PUBLISHER] == "Sega"
    assert meta.fields[ProviderField.AGE_RATING] == "PEGI 3"

    rd = meta.fields[ProviderField.RELEASE_DATE]
    assert rd.year == 1991 and rd.month == 6  # earliest stamp
    assert (
        meta.fields[ProviderField.COVER]
        == "https://images.igdb.com/igdb/image/upload/t_cover_big/co1234abc.jpg"
    )
    assert meta.cover_url == meta.fields[ProviderField.COVER]


async def test_get_game_unknown_id_raises_not_found(
    igdb_client: httpx.AsyncClient, oauth_response: dict[str, Any]
) -> None:
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "id", "client_secret": "secret"})

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=oauth_response)
        )
        respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(200, json=[])
        )
        with pytest.raises(NotFoundError):
            await provider.get_game("999999")


async def test_get_cover_returns_bytes(
    igdb_client: httpx.AsyncClient, oauth_response: dict[str, Any]
) -> None:
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "id", "client_secret": "secret"})

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=oauth_response)
        )
        respx.post("https://api.igdb.com/v4/games").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": 1234, "name": "Sonic", "cover": {"image_id": "abc"}}],
            )
        )
        respx.get(
            "https://images.igdb.com/igdb/image/upload/t_cover_big/abc.jpg"
        ).mock(return_value=httpx.Response(200, content=b"jpeg-bytes", headers={"content-type": "image/jpeg"}))

        data, content_type = await provider.get_cover("1234")

    assert data == b"jpeg-bytes"
    assert content_type == "image/jpeg"


# ---------------------------------------------------------------------------
# T026 — platform mapping
# ---------------------------------------------------------------------------


def test_platform_mapping_genesis_is_29(igdb_client: httpx.AsyncClient) -> None:
    provider = _make_provider(client=igdb_client)
    assert provider.get_platform_mapping("genesis") == 29


def test_platform_mapping_unknown_returns_none(igdb_client: httpx.AsyncClient) -> None:
    # Slice 411 widened the default mapping (psx, ps2, ngc, dc
    # etc. are all mapped now); pick a slug that really doesn't
    # match anything to exercise the None branch.
    provider = _make_provider(client=igdb_client)
    assert provider.get_platform_mapping("unknown-slug-xyz") is None


def test_platform_mapping_can_be_overridden_via_configure(
    igdb_client: httpx.AsyncClient,
) -> None:
    provider = _make_provider(client=igdb_client)
    provider.configure(
        {
            "client_id": "id",
            "client_secret": "secret",
            "platform_mapping": {"psx": 7, "genesis": 999},
        }
    )
    assert provider.get_platform_mapping("psx") == 7
    # Override wins.
    assert provider.get_platform_mapping("genesis") == 999
    # Defaults still present for non-overridden slugs.
    assert provider.get_platform_mapping("snes") == 19


# ---------------------------------------------------------------------------
# Self-registration
# ---------------------------------------------------------------------------


def test_igdb_is_self_registered() -> None:
    from romarr.metadata import PROVIDER_REGISTRY

    assert "igdb" in PROVIDER_REGISTRY
    assert PROVIDER_REGISTRY["igdb"] is IGDBProvider


# ---------------------------------------------------------------------------
# Header / body shape
# ---------------------------------------------------------------------------


async def test_query_carries_authorization_and_client_id_headers(
    igdb_client: httpx.AsyncClient, oauth_response: dict[str, Any]
) -> None:
    """The IGDB POST MUST send both Client-ID and Bearer headers."""
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "id-1", "client_secret": "secret"})

    captured: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=[])

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=oauth_response)
        )
        respx.post("https://api.igdb.com/v4/games").mock(side_effect=_record)

        await provider.search_games("sonic", platform_slug="genesis")

    assert captured, "IGDB POST was not invoked"
    request = captured[-1]
    assert request.headers["client-id"] == "id-1"
    assert request.headers["authorization"] == "Bearer twitch-bearer-1"
    body = request.content.decode("utf-8")
    assert "platforms = (29)" in body  # the genesis mapping was applied
    # Sanity: Apicalypse "fields" clause present.
    assert "fields" in body


# ---------------------------------------------------------------------------
# Sanity round-trip — JSON payload survives end-to-end
# ---------------------------------------------------------------------------


async def test_full_search_then_get_round_trip(
    igdb_client: httpx.AsyncClient, oauth_response: dict[str, Any]
) -> None:
    provider = _make_provider(client=igdb_client)
    provider.configure({"client_id": "id", "client_secret": "secret"})

    with respx.mock:
        respx.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=oauth_response)
        )

        def _route(request: httpx.Request) -> httpx.Response:
            body = request.content.decode("utf-8")
            if "where id = " in body:
                return httpx.Response(
                    200,
                    json=[{"id": 1234, "name": "Sonic the Hedgehog"}],
                )
            return httpx.Response(
                200, json=[{"id": 1234, "name": "Sonic the Hedgehog"}]
            )

        respx.post("https://api.igdb.com/v4/games").mock(side_effect=_route)

        results = await provider.search_games("Sonic the Hedgehog")
        assert len(results) == 1
        meta = await provider.get_game(results[0].provider_game_id)

    assert meta.fields[ProviderField.TITLE] == "Sonic the Hedgehog"


# ---------------------------------------------------------------------------
# Smoke — escape special characters in query
# ---------------------------------------------------------------------------


def test_escape_quotes_and_backslashes() -> None:
    from romarr.metadata.providers.igdb import _escape

    assert _escape('Hello "World"') == 'Hello \\"World\\"'
    assert _escape("path\\to\\file") == "path\\\\to\\\\file"


