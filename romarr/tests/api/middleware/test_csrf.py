"""CSRF middleware tests (T021, T022, T023, FR-026 / FR-027 / FR-028).

The middleware enforces double-submit-cookie CSRF on mutating
methods when ``Settings.csrf_protect`` is True. Defaults to
disabled (existing test suite uses cookie session + POSTs
without a CSRF header), so these tests build inline FastAPI apps
with the middleware enabled directly rather than going through
the create_app() flag.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from romarr.api.middleware import register_csrf


def _build_app() -> FastAPI:
    """Minimal FastAPI app with CSRF enabled and a few routes."""
    app = FastAPI()
    register_csrf(app, enabled=True)

    @app.get("/safe")
    async def safe() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/protected")
    async def protected() -> dict[str, str]:
        return {"created": "yes"}

    @app.post("/api/v3/auth/login")
    async def login() -> dict[str, str]:
        return {"ok": "yes"}

    return app


# ---------------------------------------------------------------------------
# T021 — cookie-authenticated POST without X-CSRF-Token → 403
# ---------------------------------------------------------------------------


def test_cookie_post_without_token_returns_403() -> None:
    """A POST that carries a cookie (i.e., the caller is acting
    as a session user) but no ``X-CSRF-Token`` header MUST
    surface HTTP 403 with errorCode ``csrf_token_missing``."""
    app = _build_app()
    with TestClient(app) as client:
        client.cookies.set("session", "fake-session-id")
        # Note: no csrf_token cookie, no X-CSRF-Token header.
        resp = client.post("/protected")
        assert resp.status_code == 403
        body = resp.json()
        assert body["errorCode"] == "csrf_token_missing"


def test_cookie_post_with_matching_token_succeeds() -> None:
    """The double-submit pattern: same value in the
    ``csrf_token`` cookie and the ``X-CSRF-Token`` header
    means the request is legitimate."""
    app = _build_app()
    with TestClient(app) as client:
        client.cookies.set("csrf_token", "matching-value-123")
        client.cookies.set("session", "fake-session-id")
        resp = client.post(
            "/protected",
            headers={"X-CSRF-Token": "matching-value-123"},
        )
        assert resp.status_code == 200


def test_cookie_post_with_mismatched_token_returns_403() -> None:
    """Mismatched cookie / header → 403. Defends against the
    classic CSRF where the attacker submits a form that pulls
    the victim's cookie but can't read the JS-set CSRF cookie."""
    app = _build_app()
    with TestClient(app) as client:
        client.cookies.set("csrf_token", "cookie-value")
        client.cookies.set("session", "fake-session-id")
        resp = client.post(
            "/protected",
            headers={"X-CSRF-Token": "different-value"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# T022 — X-Api-Key bypass
# ---------------------------------------------------------------------------


def test_apikey_header_bypasses_csrf() -> None:
    """API-key callers bypass — the ``X-Api-Key`` header isn't
    auto-attached by the browser to cross-origin requests."""
    app = _build_app()
    with TestClient(app) as client:
        # No CSRF cookie, no X-CSRF-Token; the API key alone is
        # enough to bypass.
        resp = client.post(
            "/protected",
            headers={"X-Api-Key": "rmk_test"},
        )
        assert resp.status_code == 200


def test_apikey_query_param_bypasses_csrf() -> None:
    """``?apikey=...`` query form bypasses too — the
    middleware checks for both header and query string per
    FR-022."""
    app = _build_app()
    with TestClient(app) as client:
        resp = client.post("/protected?apikey=rmk_test")
        assert resp.status_code == 200


def test_bearer_jwt_bypasses_csrf() -> None:
    """JWT Bearer tokens — same bypass reasoning as API keys."""
    app = _build_app()
    with TestClient(app) as client:
        resp = client.post(
            "/protected",
            headers={"Authorization": "Bearer some.jwt.token"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# T023 — GET bypass
# ---------------------------------------------------------------------------


def test_get_request_bypasses_csrf() -> None:
    """Safe methods don't mutate state; CSRF doesn't apply.
    GET passes through with no header / cookie."""
    app = _build_app()
    with TestClient(app) as client:
        resp = client.get("/safe")
        assert resp.status_code == 200


def test_options_preflight_bypasses_csrf() -> None:
    """OPTIONS preflight (CORS) bypasses too — the actual
    mutation comes on the follow-up POST, which IS checked."""
    app = _build_app()
    with TestClient(app) as client:
        resp = client.options(
            "/protected",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        # FastAPI without CORS middleware returns 405 for OPTIONS;
        # the point is that CSRF doesn't 403 it.
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Bootstrap path bypass
# ---------------------------------------------------------------------------


def test_login_endpoint_bypasses_csrf() -> None:
    """``POST /api/v3/auth/login`` is a bootstrap endpoint —
    the caller doesn't have a session cookie yet, so CSRF
    doesn't apply. Without this bypass the login form itself
    couldn't submit."""
    app = _build_app()
    with TestClient(app) as client:
        # No CSRF cookie or header — but login should succeed.
        resp = client.post("/api/v3/auth/login")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Disabled flag is a no-op
# ---------------------------------------------------------------------------


def test_disabled_middleware_passes_everything_through() -> None:
    """``register_csrf(enabled=False)`` makes the middleware a
    no-op — POSTs without any CSRF artefacts succeed. This is
    the default at boot until the spec 014 frontend wires
    cookie-reading."""
    app = FastAPI()
    register_csrf(app, enabled=False)

    @app.post("/anything")
    async def anything() -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app) as client:
        client.cookies.set("session", "fake")
        resp = client.post("/anything")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Anonymous POST (no cookie / no api-key) is still 403 — defensive
# ---------------------------------------------------------------------------


def test_anonymous_post_with_no_credentials_still_403() -> None:
    """Even without a session cookie, a POST without a CSRF
    header trips the guard. The downstream handler would 401
    anyway (no auth), but the CSRF middleware short-circuits
    earlier — defends against e.g. cross-origin form POSTs
    that don't carry credentials but still hit the route."""
    app = _build_app()
    with TestClient(app) as client:
        resp = client.post("/protected")
        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "csrf_token_missing"
