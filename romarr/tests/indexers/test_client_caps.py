"""NewznabClient ``caps()`` tests (T028)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from romarr.indexers import NewznabClient


def _make_client(
    *,
    base_url: str = "https://indexer.test",
    api_key: str | None = "API-KEY",
    client: httpx.AsyncClient | None = None,
) -> NewznabClient:
    return NewznabClient(
        indexer_id=1,
        name="Test Indexer",
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=5,
        client=client,
    )


@pytest.mark.asyncio
async def test_caps_happy_path(
    torznab_response: Callable[[str], bytes],
) -> None:
    body = torznab_response("torznab_caps/valid_full.xml")

    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            route = respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(200, content=body)
            )
            caps = await client.caps()

    assert route.called
    assert caps.server == "Test Indexer"
    assert caps.searching["search"]["available"] is True
    assert 1060 in caps.categories


@pytest.mark.asyncio
async def test_caps_includes_apikey_in_query() -> None:
    """The api_key is forwarded as ``apikey=<value>`` on every call."""
    captured: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            content=b"<?xml version='1.0'?><caps><server title='X'/></caps>",
        )

    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(side_effect=_record)
            await client.caps()

    assert captured
    params = dict(captured[-1].url.params)
    assert params["t"] == "caps"
    assert params["apikey"] == "API-KEY"


@pytest.mark.asyncio
async def test_caps_omits_apikey_when_none() -> None:
    captured: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            content=b"<?xml version='1.0'?><caps><server title='X'/></caps>",
        )

    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport, api_key=None)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(side_effect=_record)
            await client.caps()

    assert "apikey" not in dict(captured[-1].url.params)
