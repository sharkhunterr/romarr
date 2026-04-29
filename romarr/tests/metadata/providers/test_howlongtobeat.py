"""HowLongToBeat provider tests (T042).

Enrichment-only — get_game returns a GameMetadata whose ``fields``
contains at most ``HLTB_MAIN`` and nothing else (FR-007).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from romarr.metadata import PROVIDER_REGISTRY, ProviderField
from romarr.metadata.errors import NotFoundError
from romarr.metadata.providers.howlongtobeat import HowLongToBeatProvider


@pytest.fixture
def hltb_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0))


def _make_provider(client: httpx.AsyncClient) -> HowLongToBeatProvider:
    p = HowLongToBeatProvider(
        rate_limit_rps=100, rate_limit_burst=100, client=client
    )
    p.configure({})
    return p


async def test_search_returns_candidates(
    hltb_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(hltb_client)
    payload = {
        "data": [
            {"game_id": 1234, "game_name": "Sonic the Hedgehog", "comp_main": 7200},
            {"game_id": 1235, "game_name": "Sonic 2", "comp_main": 9000},
        ]
    }

    with respx.mock:
        respx.post("https://howlongtobeat.com/api/search").mock(
            return_value=httpx.Response(200, json=payload)
        )
        results = await p.search_games("Sonic")

    assert {r.title for r in results} == {"Sonic the Hedgehog", "Sonic 2"}
    assert results[0].provider_game_id == "1234"


async def test_get_game_populates_only_hltb_main(
    hltb_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(hltb_client)

    payload = {
        "data": [
            {"game_id": 1234, "game_name": "Sonic the Hedgehog", "comp_main": 7200},
            {"game_id": 999, "game_name": "Other", "comp_main": 100},
        ]
    }
    with respx.mock:
        respx.post("https://howlongtobeat.com/api/search").mock(
            return_value=httpx.Response(200, json=payload)
        )
        meta = await p.get_game("1234")

    # FR-007: HLTB only contributes hltb_main; nothing else.
    assert set(meta.fields.keys()) == {ProviderField.HLTB_MAIN}
    # 7200 seconds → 120 minutes.
    assert meta.fields[ProviderField.HLTB_MAIN] == 120


async def test_get_game_unknown_id_raises_not_found(
    hltb_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(hltb_client)
    with respx.mock:
        respx.post("https://howlongtobeat.com/api/search").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        with pytest.raises(NotFoundError):
            await p.get_game("999")


async def test_get_cover_raises_not_implemented(
    hltb_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(hltb_client)
    with pytest.raises(NotImplementedError):
        await p.get_cover("1")


async def test_zero_main_duration_omitted(
    hltb_client: httpx.AsyncClient,
) -> None:
    """Games without a recorded main-story time leave the field unset
    rather than persisting a sentinel zero."""
    p = _make_provider(hltb_client)
    with respx.mock:
        respx.post("https://howlongtobeat.com/api/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"game_id": 7, "game_name": "Empty", "comp_main": 0}
                    ]
                },
            )
        )
        meta = await p.get_game("7")
    assert meta.fields == {}


def test_self_registered() -> None:
    assert PROVIDER_REGISTRY.get("howlongtobeat") is HowLongToBeatProvider


def test_capabilities_only_hltb_main() -> None:
    cap = HowLongToBeatProvider.capabilities
    assert cap.contributable_fields == frozenset({ProviderField.HLTB_MAIN})
    assert cap.invoked_in_scan is True


def test_search_uses_browser_user_agent() -> None:
    """HLTB blocks default httpx UA — assert we set a Chrome-like header."""
    from romarr.metadata.providers.howlongtobeat import _DEFAULT_HEADERS

    assert "Mozilla/5.0" in _DEFAULT_HEADERS["User-Agent"]
    assert "Chrome" in _DEFAULT_HEADERS["User-Agent"]
