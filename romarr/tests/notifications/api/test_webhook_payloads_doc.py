"""Webhook-payloads doc endpoint test (T067)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_webhook_payloads_doc_returns_markdown(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get(
        "/api/v3/notification/webhook-payloads.md"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    body = response.text
    # Sanity: the document must reference the canonical Sonarr
    # remap targets so consumers can lock the contract.
    assert "series.title" in body
    assert "tvdbId" in body
    assert "FR-006a" in body


@pytest.mark.asyncio
async def test_webhook_payloads_doc_is_anonymous(
    api_client: httpx.AsyncClient,
) -> None:
    """The doc URL is a public reference — no auth required."""
    response = await api_client.get(
        "/api/v3/notification/webhook-payloads.md"
    )
    assert response.status_code == 200
