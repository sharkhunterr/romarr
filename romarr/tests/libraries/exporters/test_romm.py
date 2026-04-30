"""RomM remote-push exporter tests (T048, T049, T050)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from romarr.config.settings import get_settings
from romarr.libraries.exporters.romm import push_to_romm
from romarr.metadata.encryption import encrypt


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def encrypted_key() -> bytes:
    return encrypt(b"my-romm-api-key")


# ---------------------------------------------------------------------------
# T048 — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_posts_with_bearer_header(
    encrypted_key: bytes,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post(
            "https://romm.local/api/platforms/42/scan"
        ).mock(return_value=httpx.Response(200, json={"ok": True}))

        outcome = await push_to_romm(
            romm_url="https://romm.local",
            encrypted_api_key=encrypted_key,
            platform_id=42,
        )

    assert outcome.success is True
    assert outcome.status_code == 200
    assert outcome.error_message is None
    assert outcome.duration_ms >= 0

    # Bearer header carried the decrypted plaintext.
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer my-romm-api-key"


@pytest.mark.asyncio
async def test_url_with_trailing_slash_normalised(encrypted_key: bytes) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("https://romm.local/api/platforms/42/scan").mock(
            return_value=httpx.Response(200)
        )
        outcome = await push_to_romm(
            romm_url="https://romm.local/",  # trailing slash
            encrypted_api_key=encrypted_key,
            platform_id=42,
        )
    assert outcome.success is True


# ---------------------------------------------------------------------------
# T049 — 503 doesn't block import (FR-015 / US9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_503_returns_failure_outcome_without_raising(
    encrypted_key: bytes,
) -> None:
    """A sustained 503 retries thrice and then surfaces as
    success=False; the caller records a warning instead of failing
    the import."""
    with respx.mock() as router:
        router.post(
            "https://romm.local/api/platforms/42/scan"
        ).mock(return_value=httpx.Response(503, text="overloaded"))

        outcome = await push_to_romm(
            romm_url="https://romm.local",
            encrypted_api_key=encrypted_key,
            platform_id=42,
        )

    assert outcome.success is False
    assert outcome.status_code is None  # raised after retries → no response captured
    assert outcome.error_message is not None
    assert "503" in outcome.error_message


@pytest.mark.asyncio
async def test_4xx_returns_failure_without_retry(encrypted_key: bytes) -> None:
    """4xx is not transient — the exporter returns immediately."""
    with respx.mock() as router:
        route = router.post(
            "https://romm.local/api/platforms/42/scan"
        ).mock(return_value=httpx.Response(401, text="unauthorized"))

        outcome = await push_to_romm(
            romm_url="https://romm.local",
            encrypted_api_key=encrypted_key,
            platform_id=42,
        )

    assert outcome.success is False
    assert outcome.status_code == 401
    assert "401" in outcome.error_message
    # No retry on 4xx — exactly one call.
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_connect_error_returns_failure_outcome(
    encrypted_key: bytes,
) -> None:
    """Even when RomM is completely unreachable, the exporter never
    raises — the caller records a warning."""
    with respx.mock() as router:
        router.post(
            "https://romm.local/api/platforms/42/scan"
        ).mock(side_effect=httpx.ConnectError("dns failure"))

        outcome = await push_to_romm(
            romm_url="https://romm.local",
            encrypted_api_key=encrypted_key,
            platform_id=42,
        )

    assert outcome.success is False
    assert outcome.status_code is None
    assert "unreachable" in (outcome.error_message or "").lower() or (
        "connecterror" in (outcome.error_message or "").lower()
    )


# ---------------------------------------------------------------------------
# Tenacity retries on transient errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovers_after_one_503(encrypted_key: bytes) -> None:
    """A single 503 followed by a 200 should ultimately succeed."""
    with respx.mock() as router:
        route = router.post(
            "https://romm.local/api/platforms/42/scan"
        ).mock(
            side_effect=[
                httpx.Response(503, text="warming up"),
                httpx.Response(200, json={"ok": True}),
            ]
        )

        outcome = await push_to_romm(
            romm_url="https://romm.local",
            encrypted_api_key=encrypted_key,
            platform_id=42,
        )

    assert outcome.success is True
    assert outcome.status_code == 200
    # Two requests went out (one retry).
    assert route.call_count == 2


# ---------------------------------------------------------------------------
# T050 — three sustained failures: surface a structured outcome
# (the actual OnHealthIssue 5-min debounce lives in spec 011's
# notification consumer; the exporter only produces the input.)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_sustained_failures_return_distinct_outcomes(
    encrypted_key: bytes,
) -> None:
    """Three calls each face a sustained failure. Each returns a
    success=False outcome the notification consumer can debounce.
    The debounce itself isn't tested here — that lives in spec 011."""
    with respx.mock() as router:
        router.post(
            "https://romm.local/api/platforms/42/scan"
        ).mock(side_effect=httpx.ConnectError("down"))

        outcomes = []
        for _ in range(3):
            outcomes.append(
                await push_to_romm(
                    romm_url="https://romm.local",
                    encrypted_api_key=encrypted_key,
                    platform_id=42,
                )
            )

    assert all(o.success is False for o in outcomes)
    assert all(o.status_code is None for o in outcomes)
