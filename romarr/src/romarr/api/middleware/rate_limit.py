"""Rate-limit middleware (T034, FR-022 / FR-023 / FR-024).

Pure-ASGI sliding-window rate limiter. Three keying strategies:

  * **Login / setup / OIDC bootstrap** — keyed by client IP.
    Brute-force defence: an attacker can't credential-stuff
    by burst-POSTing 1000 passwords from one host.
  * **Default (every other endpoint)** — keyed by API key
    plaintext (or session cookie value as a fallback). Rate
    limits per-operator rather than per-IP so operators
    behind a NAT don't share a single budget.
  * **Exempt paths** — ``/api/v3/health`` is unconditionally
    exempt; cluster orchestrators and uptime probes hit it
    every few seconds.

The default state is **disabled** (``Settings.rate_limit_enabled
= False``) so the existing test suite (which fires repeated
POSTs at /login / /setup) doesn't 429 on the 6th call.
Production deployments flip ``ROMARR_RATE_LIMIT_ENABLED=true``.

Implementation: in-memory dict keyed by ``(strategy, key)`` →
``deque`` of request timestamps. Sliding 60-second window.
Single-process — for multi-replica deployments, the next slice
swaps the in-memory backing for Redis (same indirection
pattern as the idempotency cache).

429 responses carry the standard ``Retry-After`` header so
sane HTTP clients back off automatically.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from threading import Lock
from typing import TYPE_CHECKING

from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    from fastapi import FastAPI

WINDOW_SECONDS = 60.0
"""Sliding-window size; matches Sonarr's documented per-minute."""

# Path-prefix → keying strategy + per-minute limit selector. The
# selector takes the resolved Settings instance so tests can
# inject custom limits without re-importing.
_LOGIN_PATHS = frozenset(
    {
        "/api/v3/auth/login",
        "/api/v3/auth/oidc/start",
        "/api/v3/auth/oidc/callback",
    }
)
_SETUP_PATHS = frozenset({"/api/v3/auth/setup"})
_EXEMPT_PATHS = frozenset({"/api/v3/health"})


def _header(headers: list[tuple[bytes, bytes]], name: str) -> str | None:
    target = name.lower().encode("latin-1")
    for h_name, h_value in headers:
        if h_name.lower() == target:
            return h_value.decode("latin-1")
    return None


def _client_ip(scope: Scope) -> str:
    """Best-effort client IP. ``X-Forwarded-For`` if present
    (the proxy stripped the chain to the first hop), otherwise
    the ASGI ``client`` tuple's host."""
    xff = _header(scope["headers"], "x-forwarded-for")
    if xff:
        # First hop is the original client.
        return xff.split(",")[0].strip()
    client = scope.get("client")
    if client and isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return "unknown"


def _api_key_or_session_key(scope: Scope) -> str:
    """The default-strategy key: API key plaintext if present,
    else the session cookie value. Falls back to the client IP
    for unauthenticated callers (defends against unauth POST
    floods)."""
    headers = scope["headers"]
    api_key = _header(headers, "x-api-key")
    if api_key:
        return f"apikey:{api_key}"
    qs = scope.get("query_string", b"").decode("latin-1", errors="ignore")
    for chunk in qs.split("&"):
        if chunk.startswith("apikey="):
            return f"apikey:{chunk.removeprefix('apikey=')}"
    cookie = _header(headers, "cookie")
    if cookie:
        for piece in cookie.split(";"):
            piece = piece.strip()
            if piece.startswith("session="):
                return f"session:{piece.removeprefix('session=')}"
    return f"ip:{_client_ip(scope)}"


def _select_strategy(scope: Scope) -> tuple[str, str] | None:
    """Pick (strategy_label, key) for ``scope``. Returns None
    when the path is exempt."""
    path = scope["path"]
    if path in _EXEMPT_PATHS:
        return None
    if path in _LOGIN_PATHS:
        return ("login", f"ip:{_client_ip(scope)}")
    if path in _SETUP_PATHS:
        return ("setup", f"ip:{_client_ip(scope)}")
    return ("default", _api_key_or_session_key(scope))


_RETRY_AFTER_BODY = (
    b'{"errorMessage":"rate limit exceeded",'
    b'"errorCode":"rate_limit_exceeded"}'
)


async def _send_429(send: Send, *, retry_after: int) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (
                    b"content-length",
                    str(len(_RETRY_AFTER_BODY)).encode("latin-1"),
                ),
                (b"retry-after", str(retry_after).encode("latin-1")),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": _RETRY_AFTER_BODY,
            "more_body": False,
        }
    )


class RateLimitMiddleware:
    """Pure-ASGI sliding-window rate limiter."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool = True,
        login_limit: int = 5,
        setup_limit: int = 1,
        default_limit: int = 100,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self._enabled = enabled
        self._limits = {
            "login": login_limit,
            "setup": setup_limit,
            "default": default_limit,
        }
        self._clock = clock
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def _check(self, strategy: str, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds). Trims the
        bucket's deque to the sliding window first, then
        compares the count against the strategy's limit."""
        limit = self._limits[strategy]
        now = self._clock()
        cutoff = now - WINDOW_SECONDS
        bucket_key = (strategy, key)

        with self._lock:
            bucket = self._buckets.setdefault(bucket_key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                # Retry-After: when the oldest in-window
                # request ages out.
                retry_after = max(1, int(bucket[0] + WINDOW_SECONDS - now))
                return False, retry_after
            bucket.append(now)
            return True, 0

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        selected = _select_strategy(scope)
        if selected is None:
            # Exempt path.
            await self.app(scope, receive, send)
            return

        strategy, key = selected
        allowed, retry_after = self._check(strategy, key)
        if not allowed:
            await _send_429(send, retry_after=retry_after)
            return
        await self.app(scope, receive, send)


def register_rate_limit(
    app: FastAPI,
    *,
    enabled: bool,
    login_limit: int = 5,
    setup_limit: int = 1,
    default_limit: int = 100,
) -> None:
    """Register :class:`RateLimitMiddleware` on ``app``. Pass
    ``enabled=False`` (the default until production deployments
    set ``ROMARR_RATE_LIMIT_ENABLED=true``) to make the
    middleware a no-op."""
    app.add_middleware(
        RateLimitMiddleware,
        enabled=enabled,
        login_limit=login_limit,
        setup_limit=setup_limit,
        default_limit=default_limit,
    )


__all__ = [
    "WINDOW_SECONDS",
    "RateLimitMiddleware",
    "register_rate_limit",
]
