"""CORS middleware tests (T019, T020, FR-030).

Verifies the same-origin-only default and the configured-origins
flow. The middleware wraps Starlette's :class:`CORSMiddleware` —
these tests pin the contract Romarr exposes via
:func:`register_cors`, not Starlette's full surface.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from romarr.api.middleware import register_cors


def _build_app(allowed_origins: list[str]) -> FastAPI:
    app = FastAPI()
    register_cors(app, allowed_origins=allowed_origins)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    return app


# ---------------------------------------------------------------------------
# T019 — empty allow-list → same-origin only (no CORS header emitted)
# ---------------------------------------------------------------------------


def test_default_same_origin_only() -> None:
    """An empty ``allowed_origins`` list means no
    ``Access-Control-Allow-Origin`` header is emitted on a
    cross-origin request — browsers reject the response per
    their default same-origin policy."""
    app = _build_app(allowed_origins=[])
    with TestClient(app) as client:
        resp = client.get(
            "/ping",
            headers={"Origin": "https://evil.example.com"},
        )
        assert resp.status_code == 200  # request reaches the route
        # …but the browser-blocking CORS header is absent.
        assert "access-control-allow-origin" not in {
            k.lower() for k in resp.headers
        }


def test_default_same_origin_blocks_preflight() -> None:
    """Preflight (``OPTIONS``) for an unknown origin returns
    HTTP 400 — Starlette's CORS middleware refuses to ack the
    preflight if no origin matches."""
    app = _build_app(allowed_origins=[])
    with TestClient(app) as client:
        resp = client.options(
            "/ping",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T020 — configured origin allow-list
# ---------------------------------------------------------------------------


def test_configured_origin_allowed() -> None:
    """A request from a permitted origin gets the
    ``Access-Control-Allow-Origin`` header echoed back."""
    app = _build_app(allowed_origins=["https://romarr.example.com"])
    with TestClient(app) as client:
        resp = client.get(
            "/ping",
            headers={"Origin": "https://romarr.example.com"},
        )
        assert resp.status_code == 200
        assert (
            resp.headers["access-control-allow-origin"]
            == "https://romarr.example.com"
        )


def test_configured_origin_rejects_other() -> None:
    """A request from an origin NOT on the allow-list omits the
    CORS header — browsers reject the response."""
    app = _build_app(allowed_origins=["https://romarr.example.com"])
    with TestClient(app) as client:
        resp = client.get(
            "/ping",
            headers={"Origin": "https://different.example.com"},
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in {
            k.lower() for k in resp.headers
        }


def test_configured_preflight_succeeds() -> None:
    """Preflight from an allowed origin returns HTTP 200 with the
    documented allow-credentials + allow-methods headers."""
    app = _build_app(allowed_origins=["https://romarr.example.com"])
    with TestClient(app) as client:
        resp = client.options(
            "/ping",
            headers={
                "Origin": "https://romarr.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200
        assert (
            resp.headers["access-control-allow-origin"]
            == "https://romarr.example.com"
        )
        assert resp.headers["access-control-allow-credentials"] == "true"
