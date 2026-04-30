"""NewznabClient ``search()`` tests (T029, T030)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from romarr.indexers import FieldProvenance, NewznabClient


def _make_client(
    base_url: str = "https://indexer.test",
    *,
    client: httpx.AsyncClient | None = None,
) -> NewznabClient:
    return NewznabClient(
        indexer_id=2,
        name="Test",
        base_url=base_url,
        api_key="K",
        timeout_seconds=5,
        client=client,
    )


@pytest.mark.asyncio
async def test_search_with_extended_attrs(
    torznab_response: Callable[[str], bytes],
) -> None:
    """T029: extended-attrs in the response carry through to SearchResult."""
    body = torznab_response("torznab_search/extended_torznab_namespace.xml")

    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(200, content=body)
            )
            results = await client.search("Sonic", categories=[1060])

    assert len(results) == 1
    item = results[0]
    assert item.region == "US"
    assert item.region_provenance == FieldProvenance.TORZNAB
    assert item.languages == ["en", "fr"]


@pytest.mark.asyncio
async def test_search_carries_query_and_categories() -> None:
    captured: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200, content=b"<?xml version='1.0'?><rss><channel/></rss>"
        )

    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(side_effect=_record)
            await client.search("Sonic 2", categories=[1060, 7010])

    assert captured
    params = dict(captured[-1].url.params)
    assert params["t"] == "search"
    assert params["q"] == "Sonic 2"
    assert params["cat"] == "1060,7010"
    assert params["limit"] == "100"  # default result_limit


@pytest.mark.asyncio
async def test_filename_fallback_fills_missing_provenance(
    torznab_response: Callable[[str], bytes],
) -> None:
    """T030: vanilla RSS (no extended attrs) → the client's filename
    fallback fills region / convention with provenance=FILENAME."""
    body = torznab_response("torznab_search/vanilla_no_extended.xml")
    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(200, content=body)
            )
            results = await client.search("Sonic")

    item = results[0]
    # Title is "Sonic the Hedgehog (USA).md" → No-Intro parser fires
    # and stamps region/convention with FILENAME provenance.
    assert item.region == "US"
    assert item.region_provenance == FieldProvenance.FILENAME
    assert item.naming_convention is not None
    assert item.naming_convention_provenance == FieldProvenance.FILENAME
