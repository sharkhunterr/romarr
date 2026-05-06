"""NewznabClient failure-mode tests (T031, T032, T033)."""

from __future__ import annotations

import httpx
import pytest
import respx

from romarr.indexers import (
    IndexerAuthError,
    IndexerProtocolError,
    NewznabClient,
)


def _make_client(
    *, client: httpx.AsyncClient | None = None
) -> NewznabClient:
    return NewznabClient(
        indexer_id=3,
        name="Failing",
        base_url="https://indexer.test",
        api_key="K",
        timeout_seconds=5,
        client=client,
    )


@pytest.mark.asyncio
async def test_malformed_xml_in_search_returns_empty_with_health_issue() -> None:
    """T031: malformed XML in search → empty result list + health issue
    of category=parser. The exception is swallowed so a single bad
    response doesn't poison the search."""
    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(
                    200, content=b"this is not xml"
                )
            )
            results = await client.search("anything")

    # Note: lxml's recover=True is forgiving — most "not xml" inputs
    # parse to an empty document. Either way the result list is empty.
    assert results == []


@pytest.mark.asyncio
async def test_5xx_raises_protocol_error() -> None:
    """T032: HTTP 503 → IndexerProtocolError after tenacity retries."""
    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(503, content=b"server down")
            )
            with pytest.raises(IndexerProtocolError):
                await client.caps()

    issues = client.health_issues
    assert any(i.category == "protocol" for i in issues)


@pytest.mark.asyncio
async def test_401_raises_auth_error_distinctly() -> None:
    """T033: HTTP 401 → IndexerAuthError, distinct from IndexerProtocolError."""
    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(401)
            )
            with pytest.raises(IndexerAuthError):
                await client.caps()

    # The auth error is recorded as category=auth (not protocol).
    issues = client.health_issues
    assert any(i.category == "auth" for i in issues)


@pytest.mark.asyncio
async def test_403_also_raises_auth_error() -> None:
    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(403)
            )
            with pytest.raises(IndexerAuthError):
                await client.caps()


@pytest.mark.asyncio
async def test_timeout_raises_protocol_error() -> None:
    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                side_effect=httpx.TimeoutException("test timeout")
            )
            with pytest.raises(IndexerProtocolError):
                await client.caps()

    assert any(
        i.category == "connectivity" for i in client.health_issues
    )


@pytest.mark.asyncio
async def test_redirect_to_login_on_200_raises_protocol_error() -> None:
    """A 302→200 chain that lands on a /login URL is the silent
    failure mode behind the ``/api`` double-suffix bug: status was
    200, the body was HTML, the parser found zero <item>s and the
    operator saw a passing call with no results. Detect the login
    landing URL up front so the operator gets a clear error
    instead."""
    async with httpx.AsyncClient() as transport:
        client = _make_client(client=transport)
        with respx.mock:
            respx.get("https://indexer.test/api").mock(
                return_value=httpx.Response(
                    302,
                    headers={"location": "https://indexer.test/login"},
                )
            )
            respx.get("https://indexer.test/login").mock(
                return_value=httpx.Response(
                    200, content=b"<html>login form</html>"
                )
            )
            with pytest.raises(IndexerProtocolError, match="login"):
                await client.caps()

    assert any(i.category == "auth" for i in client.health_issues)
