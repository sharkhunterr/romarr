"""Sonarr-format webhook target (FR-006, FR-007).

Apprise is the unified backend for "send a chat message" / push-
notification targets, but Notifiarr / Homepage / Tautulli expect
to receive a Sonarr v3 webhook envelope at a configured HTTP URL.
Romarr supports that path natively via this module rather than
through Apprise's generic ``json://`` so we control the retry
schedule and the byte shape of the body (see
:mod:`romarr.notifications.templates.payload_builders` for the
remap).

Retry policy (FR-007):

  * 3 attempts total at 1 s → 5 s → 30 s backoff.
  * Retry on HTTP 5xx, ``httpx.RequestError`` (DNS, TCP, TLS).
  * Do NOT retry on 4xx — that's a configuration mistake; one
    failure is enough to mark ``last_status='failed'``.

The retry schedule is implemented via ``tenacity.AsyncRetrying``
with explicit per-attempt waits rather than exponential because
the spec calls out the exact 1/5/30 cadence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from romarr.notifications.errors import WebhookRetryExhausted

if TYPE_CHECKING:
    from collections.abc import Iterable

    from romarr.notifications.models import Notification


_BACKOFF_SCHEDULE_SECONDS: tuple[int, ...] = (1, 5, 30)
"""Wait between attempts. Spec 011 FR-007 mandates this exact
cadence; keep the tuple in sync with both the schedule check and
the test fixtures' freezegun assertions."""


@dataclass(frozen=True)
class WebhookSendResult:
    """Outcome of one :func:`send_webhook` call.

    Mirrors :class:`AppriseSendResult`'s shape so the dispatcher
    records both targets through one audit code-path.
    """

    success: bool
    status_code: int | None = None
    error_message: str | None = None
    attempts: int = 0


class _RetryableHTTPError(Exception):
    """Internal: raised inside one attempt to signal "5xx, retry."
    Caught by ``retry_if_exception_type``."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(
            f"upstream returned {response.status_code} {response.reason_phrase}"
        )
        self.response = response


def _wait_schedule(
    schedule: Iterable[int] = _BACKOFF_SCHEDULE_SECONDS,
) -> wait_fixed:
    """Tenacity's ``wait_fixed`` consults the attempt index, so we
    wrap with a small adapter that returns the schedule entry for
    the current attempt. ``wait_fixed`` is reused as the base so
    behaviour outside the schedule (defensive default) is well-
    defined."""
    schedule_tuple: tuple[int, ...] = tuple(schedule)

    class _Wait(wait_fixed):
        def __init__(self) -> None:
            super().__init__(0)

        def __call__(self, retry_state: Any) -> float:
            idx = int(retry_state.attempt_number) - 1
            if 0 <= idx < len(schedule_tuple):
                return float(schedule_tuple[idx])
            return float(schedule_tuple[-1])

    return _Wait()


async def send_webhook(
    *,
    notification: Notification,
    target_url: str,
    payload_dict: dict[str, Any],
    timeout: float = 10.0,
) -> WebhookSendResult:
    """POST ``payload_dict`` as JSON to ``target_url`` with the
    spec-mandated 1/5/30 s retry schedule.

    Returns a :class:`WebhookSendResult` rather than raising on
    failure; the dispatcher records the outcome on the
    ``notification`` row's audit columns. The single exception
    path is :class:`WebhookRetryExhausted`, raised after all
    three attempts fail — callers that need the structured
    failure metadata catch it; callers that just want the
    success/failure boolean read the result.

    The notification ORM is reserved for future use (signed
    webhooks, custom headers per target); the body is fully
    derived from ``payload_dict``.
    """
    attempts_made = 0
    last_response: httpx.Response | None = None
    last_exc: Exception | None = None

    async def _attempt() -> httpx.Response:
        nonlocal attempts_made, last_response
        attempts_made += 1
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                target_url,
                json=payload_dict,
                headers={"User-Agent": "Romarr/0.11"},
            )
        last_response = response
        if 500 <= response.status_code < 600:
            raise _RetryableHTTPError(response)
        return response

    retryer = AsyncRetrying(
        stop=stop_after_attempt(len(_BACKOFF_SCHEDULE_SECONDS)),
        wait=_wait_schedule(),
        retry=retry_if_exception_type(
            (_RetryableHTTPError, httpx.RequestError)
        ),
        reraise=False,
    )

    try:
        async for attempt in retryer:
            with attempt:
                await _attempt()
    except RetryError as exc:
        if exc.last_attempt:
            last_exc_raw = exc.last_attempt.exception()
            last_exc = (
                last_exc_raw
                if isinstance(last_exc_raw, Exception)
                else None
            )
        else:
            last_exc = exc
        # Fall through to "all attempts failed" branch below.

    if attempts_made and last_response is not None and last_response.is_success:
        return WebhookSendResult(
            success=True,
            status_code=last_response.status_code,
            attempts=attempts_made,
        )

    # 4xx (non-retryable) or exhausted retries.
    if last_response is not None and not last_response.is_success:
        message = (
            f"webhook returned {last_response.status_code} "
            f"{last_response.reason_phrase}"
        )
        # Non-retryable 4xx: still surface as failed without the
        # custom exception (the dispatcher records the audit row).
        if last_response.status_code < 500:
            return WebhookSendResult(
                success=False,
                status_code=last_response.status_code,
                error_message=message,
                attempts=attempts_made,
            )
        # 5xx exhausted: raise so the caller knows retries were
        # used up. The dispatcher catches and audit-logs.
        raise WebhookRetryExhausted(message)

    # Connection-level failure across all attempts.
    err_msg = (
        f"{last_exc.__class__.__name__}: {last_exc}"
        if last_exc
        else "webhook delivery failed before any response"
    )
    raise WebhookRetryExhausted(err_msg)


__all__ = ["WebhookSendResult", "send_webhook"]
