"""Webhook retry tests (T024-T026, FR-007, SC-002).

The webhook target retries 3 times total on HTTP 5xx /
connection errors with the spec-mandated cadence
1 s → 5 s → 30 s. Tests use respx to mock the upstream and
patch tenacity's sleep so freezegun isn't required to assert
the schedule — measuring elapsed wall-clock time would make
the suite flaky.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from romarr.notifications.errors import WebhookRetryExhausted
from romarr.notifications.models import Notification
from romarr.notifications.webhook import send_webhook

_TARGET = "https://hooks.example/test"


def _bare_notification() -> Notification:
    return Notification(
        name="hook",
        apprise_url_encrypted=b"",
        apprise_url_scheme="json",
    )


@pytest.fixture
def captured_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace tenacity's sleep with a recorder so the test can
    assert the schedule without spending real wall-clock time
    or pulling in freezegun."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(float(seconds))

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return sleeps


# ---------------------------------------------------------------------------
# T024 — 5xx triggers the documented backoff schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_503_retries_with_backoff(
    captured_sleeps: list[float],
) -> None:
    """3 attempts; tenacity sleeps 1 s after attempt 1, 5 s after
    attempt 2; the 30 s slot is documented but never reached
    because :func:`send_webhook` stops after the 3rd attempt."""
    with respx.mock(assert_all_called=False) as router:
        route = router.post(_TARGET).mock(
            return_value=httpx.Response(503, text="upstream borked")
        )
        with pytest.raises(WebhookRetryExhausted):
            await send_webhook(
                notification=_bare_notification(),
                target_url=_TARGET,
                payload_dict={"eventType": "Test"},
            )
        assert route.call_count == 3
    # Two waits between three attempts; 30 s is unused.
    assert captured_sleeps == [1, 5]


# ---------------------------------------------------------------------------
# T025 — after 3 failures the notification is marked failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_after_three_failures_raises_with_structured_error(
    captured_sleeps: list[float],
) -> None:
    """``WebhookRetryExhausted`` carries a structured message so
    the dispatcher can record it on ``notification.last_error``."""
    with respx.mock(assert_all_called=False) as router:
        router.post(_TARGET).mock(
            return_value=httpx.Response(503, text="nope")
        )
        with pytest.raises(WebhookRetryExhausted) as exc_info:
            await send_webhook(
                notification=_bare_notification(),
                target_url=_TARGET,
                payload_dict={"eventType": "Test"},
            )
        assert "503" in str(exc_info.value)


@pytest.mark.asyncio
async def test_connection_error_retries_and_raises(
    captured_sleeps: list[float],
) -> None:
    """Connection-level failures (DNS, TCP, TLS) are retryable
    per FR-007; after exhaustion the wrapper raises
    ``WebhookRetryExhausted`` with the underlying exception
    class name embedded."""
    with respx.mock(assert_all_called=False) as router:
        router.post(_TARGET).mock(
            side_effect=httpx.ConnectError("dns failure")
        )
        with pytest.raises(WebhookRetryExhausted) as exc_info:
            await send_webhook(
                notification=_bare_notification(),
                target_url=_TARGET,
                payload_dict={"eventType": "Test"},
            )
        assert "ConnectError" in str(exc_info.value)
    assert captured_sleeps == [1, 5]


# ---------------------------------------------------------------------------
# T026 — happy path: no backoff inserted on first-try success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_immediate_success_no_backoff(
    captured_sleeps: list[float],
) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.post(_TARGET).mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = await send_webhook(
            notification=_bare_notification(),
            target_url=_TARGET,
            payload_dict={"eventType": "Test"},
        )
        assert route.call_count == 1
    assert result.success is True
    assert result.status_code == 200
    assert result.attempts == 1
    assert captured_sleeps == []


@pytest.mark.asyncio
async def test_recovers_after_one_503(
    captured_sleeps: list[float],
) -> None:
    """Transient 5xx that clears on the second attempt: result
    reports success and the audit row records 2 attempts."""
    responses = [
        httpx.Response(503, text="please retry"),
        httpx.Response(200, json={"ok": True}),
    ]

    def side_effect(request: Any) -> httpx.Response:
        return responses.pop(0)

    with respx.mock(assert_all_called=False) as router:
        router.post(_TARGET).mock(side_effect=side_effect)
        result = await send_webhook(
            notification=_bare_notification(),
            target_url=_TARGET,
            payload_dict={"eventType": "Test"},
        )
    assert result.success is True
    assert result.attempts == 2
    assert captured_sleeps == [1]


# ---------------------------------------------------------------------------
# 4xx is NOT retryable — operator-side mistake should fail fast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_does_not_retry(captured_sleeps: list[float]) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.post(_TARGET).mock(
            return_value=httpx.Response(404, text="missing")
        )
        result = await send_webhook(
            notification=_bare_notification(),
            target_url=_TARGET,
            payload_dict={"eventType": "Test"},
        )
        assert route.call_count == 1
    assert result.success is False
    assert result.status_code == 404
    assert captured_sleeps == []
