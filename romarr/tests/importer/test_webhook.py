"""Webhook endpoint tests (T017-T019, FR-002 / SC-008)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from romarr.config.settings import get_settings
from romarr.importer.webhook import (
    WebhookPayload,
    configure_dispatcher,
    reset_rate_limit_state,
)


@pytest.fixture(autouse=True)
def _patch_token(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("ROMARR_IMPORTER_WEBHOOK_TOKEN", "good-token")
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    reset_rate_limit_state()
    yield
    configure_dispatcher(None)
    get_settings.cache_clear()
    reset_rate_limit_state()


def _payload() -> dict[str, str]:
    return {
        "download_client_native_id": "info-hash-abc",
        "download_client_kind": "qbittorrent",
    }


# ---------------------------------------------------------------------------
# T017 — bad token returns 401 in constant time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_token_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/webhook/download-complete",
        json=_payload(),
        headers={"X-Romarr-Webhook-Token": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "invalid_token"


@pytest.mark.asyncio
async def test_missing_token_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/webhook/download-complete", json=_payload()
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_disabled_webhook_returns_401(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty token in settings ⇒ webhook closed; every call 401s
    even when the caller sends a token (defensive: a misconfigured
    deployment shouldn't accept whatever the operator's hook sends)."""
    monkeypatch.setenv("ROMARR_IMPORTER_WEBHOOK_TOKEN", "")
    get_settings.cache_clear()

    response = await api_client.post(
        "/api/v3/webhook/download-complete",
        json=_payload(),
        headers={"X-Romarr-Webhook-Token": "anything"},
    )
    assert response.status_code == 401
    assert response.json()["errorCode"] == "webhook_disabled"


# ---------------------------------------------------------------------------
# T018 — rate limit (10/min/IP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_returns_429_after_burst(
    api_client: httpx.AsyncClient,
) -> None:
    """11 valid requests in <60 s ⇒ the 11th gets 429."""
    for _ in range(10):
        ok = await api_client.post(
            "/api/v3/webhook/download-complete",
            json=_payload(),
            headers={"X-Romarr-Webhook-Token": "good-token"},
        )
        assert ok.status_code == 202

    blocked = await api_client.post(
        "/api/v3/webhook/download-complete",
        json=_payload(),
        headers={"X-Romarr-Webhook-Token": "good-token"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["errorCode"] == "rate_limited"


# ---------------------------------------------------------------------------
# T019 — happy path: 202 immediately + dispatch enqueued
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_token_returns_202_and_dispatches(
    api_client: httpx.AsyncClient,
) -> None:
    received: list[WebhookPayload] = []

    async def recorder(payload: WebhookPayload) -> None:
        received.append(payload)

    configure_dispatcher(recorder)
    response = await api_client.post(
        "/api/v3/webhook/download-complete",
        json=_payload(),
        headers={"X-Romarr-Webhook-Token": "good-token"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    assert body["download_client_native_id"] == "info-hash-abc"

    # Give the fire-and-forget task a moment to fire.
    import asyncio

    await asyncio.sleep(0.05)
    assert len(received) == 1
    assert received[0].download_client_native_id == "info-hash-abc"


@pytest.mark.asyncio
async def test_no_dispatcher_configured_still_returns_202(
    api_client: httpx.AsyncClient,
) -> None:
    """No dispatcher attached ⇒ webhook still publishes 202; the
    payload is silently dropped. Useful during boot when the
    orchestrator hasn't wired itself yet."""
    response = await api_client.post(
        "/api/v3/webhook/download-complete",
        json=_payload(),
        headers={"X-Romarr-Webhook-Token": "good-token"},
    )
    assert response.status_code == 202


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_native_id_returns_422(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/webhook/download-complete",
        json={"download_client_kind": "qbittorrent"},
        headers={"X-Romarr-Webhook-Token": "good-token"},
    )
    assert response.status_code == 422
