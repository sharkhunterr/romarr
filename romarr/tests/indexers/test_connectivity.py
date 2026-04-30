"""Connectivity tester tests (T045, T046)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from romarr.indexers import NewznabClient
from romarr.indexers import test_connectivity as connectivity_probe


def _make_client(
    *, client: httpx.AsyncClient | None = None
) -> NewznabClient:
    return NewznabClient(
        indexer_id=1,
        name="Test",
        base_url="https://indexer.test",
        api_key=None,
        timeout_seconds=5,
        client=client,
    )


@pytest.mark.asyncio
async def test_caps_only_when_search_block_absent(
    torznab_response: Callable[[str], bytes],
) -> None:
    """T045: caps with no ``<searching>`` reports caps_ok=True but
    leaves search_ok=None and adds an operator-actionable message."""
    body = torznab_response("torznab_caps/no_search_block.xml")

    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(200, content=body)
            )
            result = await connectivity_probe(client)

    assert result.ok is True
    assert result.caps_ok is True
    assert result.search_ok is None
    assert "search" in (result.message or "").lower()


@pytest.mark.asyncio
async def test_caps_then_search_full_success(
    torznab_response: Callable[[str], bytes],
) -> None:
    """T046: caps reports search support; tester also runs a search
    and reports both as OK."""
    caps_body = torznab_response("torznab_caps/valid_full.xml")

    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)

        def _route(request: httpx.Request) -> httpx.Response:
            t = request.url.params.get("t")
            if t == "caps":
                return httpx.Response(200, content=caps_body)
            if t == "search":
                return httpx.Response(
                    200, content=b"<?xml version='1.0'?><rss><channel/></rss>"
                )
            return httpx.Response(404)

        with respx.mock:
            respx.get("https://indexer.test/api").mock(side_effect=_route)
            result = await connectivity_probe(client)

    assert result.ok is True
    assert result.caps_ok is True
    assert result.search_ok is True
    assert result.category == "ok"


@pytest.mark.asyncio
async def test_caps_failure_returns_structured_result() -> None:
    """A 401 on caps does NOT raise; it reports category=auth."""
    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(401)
            )
            result = await connectivity_probe(client)

    assert result.ok is False
    assert result.caps_ok is False
    assert result.category == "auth"


@pytest.mark.asyncio
async def test_caps_succeeds_search_fails_with_auth(
    torznab_response: Callable[[str], bytes],
) -> None:
    caps_body = torznab_response("torznab_caps/valid_full.xml")

    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)

        def _route(request: httpx.Request) -> httpx.Response:
            t = request.url.params.get("t")
            if t == "caps":
                return httpx.Response(200, content=caps_body)
            return httpx.Response(401)

        with respx.mock:
            respx.get("https://indexer.test/api").mock(side_effect=_route)
            result = await connectivity_probe(client)

    assert result.ok is False
    assert result.caps_ok is True
    assert result.search_ok is False
    assert result.category == "auth"
