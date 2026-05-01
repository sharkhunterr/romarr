"""GZip middleware tests (T018, FR-029).

Verifies the 1 KB threshold contract: bodies below the threshold
are sent uncompressed; bodies at or above are gzip-encoded.
The threshold is configurable per-app via
:func:`register_gzip(min_size_bytes=...)`, but production reads it
from :attr:`Settings.gzip_min_size_bytes` (default 1024).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from romarr.api.middleware import register_gzip


def _build_app(min_size_bytes: int) -> FastAPI:
    app = FastAPI()
    register_gzip(app, min_size_bytes=min_size_bytes)

    @app.get("/small")
    async def small() -> dict[str, str]:
        return {"x": "y"}

    @app.get("/big")
    async def big() -> dict[str, str]:
        # Inflate the body well past 1 KB. The literal string is
        # repeated rather than encoded with high entropy so gzip
        # actually compresses it — random bytes wouldn't.
        return {"payload": "compress-me-" * 200}

    return app


def test_small_body_not_compressed() -> None:
    """A body well under the threshold passes through plain."""
    app = _build_app(min_size_bytes=1024)
    with TestClient(app) as client:
        resp = client.get("/small", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200
        assert resp.headers.get("content-encoding") != "gzip"


def test_large_body_compressed() -> None:
    """A body above the threshold is returned gzipped."""
    app = _build_app(min_size_bytes=1024)
    with TestClient(app) as client:
        resp = client.get("/big", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200
        assert resp.headers.get("content-encoding") == "gzip"
        # httpx auto-decodes gzip; the round-trip works.
        assert resp.json()["payload"].startswith("compress-me-")


def test_gzip_skipped_when_client_does_not_accept() -> None:
    """A client that doesn't advertise gzip Accept-Encoding gets
    plain bytes regardless of body size — Starlette's
    GZipMiddleware checks the request header before compressing."""
    app = _build_app(min_size_bytes=1024)
    with TestClient(app) as client:
        # Default httpx adds Accept-Encoding: gzip, deflate; force it
        # off explicitly. ``identity`` means "no compression".
        resp = client.get("/big", headers={"Accept-Encoding": "identity"})
        assert resp.status_code == 200
        assert resp.headers.get("content-encoding") != "gzip"


def test_threshold_can_be_set_to_zero() -> None:
    """``min_size_bytes=0`` opts in to compressing every response —
    the operator-tunable extreme of FR-029."""
    app = _build_app(min_size_bytes=0)
    with TestClient(app) as client:
        resp = client.get("/small", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200
        assert resp.headers.get("content-encoding") == "gzip"
