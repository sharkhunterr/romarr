"""CSRF middleware (T033, FR-026 / FR-027 / FR-028).

Implements the standard double-submit-cookie CSRF defence for
cookie-session callers. The spec contract:

  * **Safe methods** (GET / HEAD / OPTIONS / TRACE) bypass —
    no state mutation, no CSRF risk.
  * **API-key callers** bypass — the X-Api-Key header is
    cross-origin-prevented by the browser's CORS policy and
    can't be forged from a victim's session.
  * **Bearer JWT callers** bypass — same reasoning as
    API-key.
  * **Bootstrap paths** (login / setup / logout / webhook)
    bypass — the caller doesn't have a session cookie yet
    (login / setup) or is token-gated separately (webhook).
  * **Cookie-session callers** must send the
    ``X-CSRF-Token`` header with a value matching the
    ``csrf_token`` cookie. Missing or mismatched →
    HTTP 403 with errorCode ``csrf_token_missing``.

The middleware is gated by :attr:`Settings.csrf_protect` so the
default deployment doesn't break the existing test suite (which
logs in via cookie session and POSTs without a CSRF header).
The spec 014 frontend wiring flips ``ROMARR_CSRF_PROTECT=true``
once the SPA reads the cookie + echoes the header on every
mutation.

Pure-ASGI implementation rather than ``BaseHTTPMiddleware`` —
it doesn't need to read the body, so the simpler form works.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    from fastapi import FastAPI

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Bootstrap paths that don't require CSRF — the caller doesn't
# have a session cookie yet (login / setup) or is token-gated
# separately (webhook). Mirrors the
# ``test_endpoint_coverage.PUBLIC_PATHS`` allow-list.
_BYPASS_PATHS = frozenset(
    {
        "/api/v3/auth/login",
        "/api/v3/auth/setup",
        "/api/v3/auth/logout",
        "/api/v3/webhook/download-complete",
    }
)


def _header(headers: list[tuple[bytes, bytes]], name: str) -> str | None:
    """Extract one header value (latin-1 decoded), case-insensitive."""
    target = name.lower().encode("latin-1")
    for h_name, h_value in headers:
        if h_name.lower() == target:
            return h_value.decode("latin-1")
    return None


def _parse_cookie_jar(raw: str | None) -> dict[str, str]:
    """Tiny RFC 6265 cookie-string parser. Sufficient for the
    ``csrf_token`` lookup; doesn't try to handle quoted-pair
    values (none of our cookies use them)."""
    jar: dict[str, str] = {}
    if not raw:
        return jar
    for chunk in raw.split(";"):
        if "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        jar[name.strip()] = value.strip()
    return jar


_FORBIDDEN_BODY = (
    b'{"errorMessage":"CSRF token missing or mismatched",'
    b'"errorCode":"csrf_token_missing"}'
)


async def _send_403(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (
                    b"content-length",
                    str(len(_FORBIDDEN_BODY)).encode("latin-1"),
                ),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": _FORBIDDEN_BODY,
            "more_body": False,
        }
    )


class CSRFMiddleware:
    """Pure-ASGI CSRF guard. See module docstring for behaviour."""

    def __init__(self, app: ASGIApp, *, enabled: bool = True) -> None:
        self.app = app
        self._enabled = enabled

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        if method in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        if scope["path"] in _BYPASS_PATHS:
            await self.app(scope, receive, send)
            return

        headers = scope["headers"]
        # API-key callers bypass — no CSRF risk because the
        # X-Api-Key header isn't auto-attached by the browser to
        # cross-origin requests.
        if (
            _header(headers, "x-api-key")
            or scope.get("query_string", b"").startswith(b"apikey=")
            or b"&apikey=" in scope.get("query_string", b"")
        ):
            await self.app(scope, receive, send)
            return

        # Bearer JWT callers bypass — same reasoning.
        auth = _header(headers, "authorization") or ""
        if auth.lower().startswith("bearer "):
            await self.app(scope, receive, send)
            return

        # Cookie-session caller — require the double-submit
        # cookie + matching X-CSRF-Token header.
        cookie_jar = _parse_cookie_jar(_header(headers, "cookie"))
        cookie_token = cookie_jar.get("csrf_token")
        header_token = _header(headers, "x-csrf-token")

        if (
            not cookie_token
            or not header_token
            or not secrets.compare_digest(cookie_token, header_token)
        ):
            await _send_403(send)
            return

        await self.app(scope, receive, send)


def register_csrf(app: FastAPI, *, enabled: bool) -> None:
    """Register :class:`CSRFMiddleware` on ``app``. Pass
    ``enabled=False`` (the default until the frontend wires
    cookie-reading + header-echoing) to make the middleware a
    no-op — registering it unconditionally simplifies the
    factory wiring."""
    app.add_middleware(CSRFMiddleware, enabled=enabled)


__all__ = ["CSRFMiddleware", "register_csrf"]
