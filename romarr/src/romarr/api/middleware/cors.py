"""CORS middleware (T032, FR-030).

Wraps Starlette's :class:`CORSMiddleware` (re-exported by FastAPI).
The allow-list comes from :attr:`Settings.cors_allowed_origins`
which reads the ``ROMARR_CORS_ALLOWED_ORIGINS`` env var as JSON.

The defaults follow the principle of least surprise:

  * empty allow-list → same-origin only (no ``Access-Control-Allow-
    Origin`` header is emitted, so cross-origin browsers reject
    the response per their default policy);
  * non-empty allow-list → only the configured origins are
    accepted; CORS preflights for other origins receive a
    standard rejection;
  * credentials are allowed (cookies + Authorization) so the
    cookie-session flow works from a browser SPA hosted on a
    permitted origin;
  * methods / headers are wildcarded to keep the allow-list
    surface small — the operator decides ORIGIN, the rest is
    pass-through.

Reverse proxies fronting Romarr should leave the allow-list empty
and pass the original Host through unchanged so same-origin
behaviour is preserved end-to-end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastapi import FastAPI


def register_cors(
    app: FastAPI, *, allowed_origins: Sequence[str]
) -> None:
    """Add :class:`CORSMiddleware` to ``app`` with the documented
    allow-list. An empty list is a safe no-op — the middleware is
    still registered, but it won't allow any cross-origin
    request, matching the FR-030 same-origin-only default."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


__all__ = ["register_cors"]
