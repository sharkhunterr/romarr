"""GZip response compression middleware (T031, FR-029).

Wraps Starlette's :class:`GZipMiddleware` (re-exported by
FastAPI). The threshold comes from
:attr:`Settings.gzip_min_size_bytes` so operators can tune it via
``ROMARR_GZIP_MIN_SIZE_BYTES``. Responses below the threshold are
sent uncompressed; responses at or above are gzipped and carry
``Content-Encoding: gzip``.

The middleware MUST be registered before any router-level
middleware that mutates the response body — Starlette runs the
last-registered middleware first, so pushing GZip in early keeps
it on the outermost layer.

Pure helper: takes a FastAPI app and the threshold; returns
nothing. Settings injection happens at the factory level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.middleware.gzip import GZipMiddleware

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_gzip(app: FastAPI, *, min_size_bytes: int) -> None:
    """Add :class:`GZipMiddleware` to ``app`` with the documented
    threshold. Idempotent at the app level — Starlette dedupes
    middleware on identity, but we don't expect repeated calls."""
    app.add_middleware(GZipMiddleware, minimum_size=min_size_bytes)


__all__ = ["register_gzip"]
