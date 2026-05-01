"""Download-complete webhook endpoint (FR-002).

POST ``/api/v3/webhook/download-complete`` is the operator's own
download client (qBittorrent's ``run external program``, SAB's
post-processing hook, etc.) telling Romarr "this download just
completed; please import it". Bypasses session auth — uses its
own bearer token from
:class:`romarr.config.settings.Settings.importer_webhook_token`.

Three defenses:

  1. **Constant-time token comparison** via
     :func:`secrets.compare_digest` so timing attacks can't
     enumerate valid tokens.
  2. **Sliding-window rate limit** of 10 requests per source IP
     per 60-second window. Returns HTTP 429 on overage.
  3. **Schema validation** via :class:`WebhookPayload`. The
     handler returns 202 ``Accepted`` immediately and dispatches
     the actual import in a background asyncio task so the
     caller's connection isn't held open during the pipeline
     (FR-002 / SC-008).

The router stays narrowly-scoped: it does **not** authenticate
via the session-cookie path, so it doesn't need
``require_admin``. The bearer token is the gate.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from romarr.importer._rate_limit import SlidingWindowLimiter

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

router = APIRouter(prefix="/api/v3/webhook", tags=["Webhooks"])


_RATE_LIMIT_WINDOW = timedelta(seconds=60)
_RATE_LIMIT_MAX = 10

# Module-level limiter — survives across requests. Reset
# between tests via the dedicated fixture.
_limiter = SlidingWindowLimiter(
    window=_RATE_LIMIT_WINDOW, max_events=_RATE_LIMIT_MAX
)

# Hold strong references to in-flight dispatch tasks so the
# asyncio loop's weakref bookkeeping doesn't garbage-collect
# them mid-import. Tasks remove themselves on completion.
_inflight: set[asyncio.Task[None]] = set()


# ---------------------------------------------------------------------------
# Request/response shapes


class WebhookPayload(BaseModel):
    """Common shape every supported download client posts.

    qBittorrent and SABnzbd have different native shapes; for
    MVP we accept the lowest-common-denominator fields and rely
    on the operator's hook script to render them. Future client
    variants (Transmission, Deluge, NZBGet) will land as a
    discriminated union.
    """

    model_config = ConfigDict(extra="ignore")

    download_client_native_id: str
    download_client_kind: Literal["qbittorrent", "sabnzbd"] = "qbittorrent"


class WebhookAcceptedResponse(BaseModel):
    """202 ACCEPTED body — the import has been queued."""

    accepted: bool = True
    download_client_native_id: str


# ---------------------------------------------------------------------------
# Token + rate-limit helpers


def _client_ip(request: Request) -> str:
    """Trust ``request.client.host`` for the rate-limit key. The
    operator's reverse proxy is responsible for ``X-Forwarded-For``
    rewriting if they front Romarr with one."""
    if request.client is None:  # pragma: no cover — TestClient sets this
        return "unknown"
    return request.client.host


def _expected_token() -> str:
    """Read the configured token from Settings. Imported lazily so
    the test fixture's monkeypatch lands before the call."""
    from romarr.config.settings import get_settings

    return get_settings().importer_webhook_token or ""


def _verify_token(provided: str | None) -> None:
    """Constant-time comparison; raises 401 on mismatch without
    leaking the expected value."""
    expected = _expected_token()
    candidate = provided or ""
    # When no token is configured, the webhook is closed (401 every call).
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "errorMessage": "webhook_disabled",
                "errorCode": "webhook_disabled",
            },
        )
    if not secrets.compare_digest(candidate, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "errorMessage": "invalid_webhook_token",
                "errorCode": "invalid_token",
            },
        )


# ---------------------------------------------------------------------------
# Background dispatch


_BackgroundDispatcher = "Callable[[WebhookPayload], Awaitable[None]]"
_dispatcher: _BackgroundDispatcher | None = None  # type: ignore[valid-type]


def configure_dispatcher(
    dispatcher: Callable[[WebhookPayload], Awaitable[None]] | None,
) -> None:
    """Inject the background dispatcher the webhook fires after a
    202. Tests pass a recording stub; production wires the
    orchestrator's ``run_import``.

    Pass ``None`` to detach (used by the test fixture)."""
    global _dispatcher
    # explicit DI surface here; configure_dispatcher is the API.
    _dispatcher = dispatcher


# ---------------------------------------------------------------------------
# Endpoint


@router.post(
    "/download-complete",
    response_model=WebhookAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary=(
        "Notify Romarr that a download is complete and ready to import. "
        "Bearer-token authenticated; rate-limited 10 req/min/IP."
    ),
)
async def download_complete(
    request: Request,
    payload: WebhookPayload,
    x_romarr_webhook_token: Annotated[str | None, Header()] = None,
) -> WebhookAcceptedResponse:
    _verify_token(x_romarr_webhook_token)

    now = datetime.now(UTC)
    if not _limiter.allow(key=_client_ip(request), now=now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "errorMessage": "webhook_rate_limit",
                "errorCode": "rate_limited",
                "details": (
                    f"max {_RATE_LIMIT_MAX} requests per "
                    f"{int(_RATE_LIMIT_WINDOW.total_seconds())} s "
                    f"per source IP"
                ),
            },
        )

    if _dispatcher is not None:
        # Fire-and-forget — the import runs after we publish 202.
        # Hold a strong ref via ``_inflight`` so the loop doesn't
        # garbage-collect the task mid-import.
        task = asyncio.create_task(_dispatcher(payload))
        _inflight.add(task)
        task.add_done_callback(_inflight.discard)

    return WebhookAcceptedResponse(
        download_client_native_id=payload.download_client_native_id
    )


def reset_rate_limit_state() -> None:
    """Clear the in-process rate-limit buckets. Test-only —
    production never calls this."""
    _limiter._events.clear()


__all__ = [
    "WebhookAcceptedResponse",
    "WebhookPayload",
    "configure_dispatcher",
    "reset_rate_limit_state",
    "router",
]
