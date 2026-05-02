"""Rate-limit middleware tests (T024, T025, T026, T027,
FR-022 / FR-023 / FR-024).

The middleware applies a sliding-window rate limit with three
keying strategies: login (per-IP), setup (per-IP), default
(per-API-key-or-session). Tests inject a controllable clock so
they don't need real-time waits.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from romarr.api.middleware.rate_limit import RateLimitMiddleware


class _Clock:
    """Manually-advanceable monotonic clock for testing."""

    def __init__(self, start: float = 1000.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def _build_app(
    *,
    login_limit: int = 5,
    setup_limit: int = 1,
    default_limit: int = 100,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    """Minimal app with the rate limiter enabled directly."""
    app = FastAPI()
    actual_clock: Callable[[], float] = clock or _Clock()
    app.add_middleware(
        RateLimitMiddleware,
        enabled=True,
        login_limit=login_limit,
        setup_limit=setup_limit,
        default_limit=default_limit,
        clock=actual_clock,
    )

    @app.post("/api/v3/auth/login")
    async def login() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/api/v3/auth/setup")
    async def setup() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/v3/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/api/v3/anything")
    async def anything() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/api/v3/anything")
    async def anything_post() -> dict[str, str]:
        return {"ok": "yes"}

    return app


# ---------------------------------------------------------------------------
# T024 — login: 5/min per IP
# ---------------------------------------------------------------------------


def test_login_allows_first_5_then_429s() -> None:
    """5 POSTs to /login from one IP succeed; the 6th returns
    429 with Retry-After (FR-022, SC-006)."""
    app = _build_app(login_limit=5)
    with TestClient(app) as client:
        for i in range(5):
            resp = client.post("/api/v3/auth/login")
            assert resp.status_code == 200, f"call {i + 1} failed"

        sixth = client.post("/api/v3/auth/login")
        assert sixth.status_code == 429
        assert sixth.json()["errorCode"] == "rate_limit_exceeded"
        assert int(sixth.headers["retry-after"]) >= 1


def test_login_window_slides_and_clears_old_attempts() -> None:
    """After the 60-second window passes, the bucket clears."""
    clock = _Clock()
    app = _build_app(login_limit=2, clock=clock)
    with TestClient(app) as client:
        assert client.post("/api/v3/auth/login").status_code == 200
        assert client.post("/api/v3/auth/login").status_code == 200
        assert client.post("/api/v3/auth/login").status_code == 429

        # Advance past the window — bucket clears.
        clock.advance(61.0)
        assert client.post("/api/v3/auth/login").status_code == 200


def test_login_keyed_by_ip_via_x_forwarded_for() -> None:
    """Different IPs (via X-Forwarded-For) get separate
    buckets — a load-balancer fronting Romarr doesn't share
    the budget across all clients."""
    app = _build_app(login_limit=2)
    with TestClient(app) as client:
        for _ in range(2):
            assert client.post(
                "/api/v3/auth/login",
                headers={"X-Forwarded-For": "10.0.0.1"},
            ).status_code == 200
        # Same IP — over budget.
        assert client.post(
            "/api/v3/auth/login",
            headers={"X-Forwarded-For": "10.0.0.1"},
        ).status_code == 429
        # Different IP — fresh budget.
        assert client.post(
            "/api/v3/auth/login",
            headers={"X-Forwarded-For": "10.0.0.2"},
        ).status_code == 200


# ---------------------------------------------------------------------------
# T025 — setup: 1/min per IP
# ---------------------------------------------------------------------------


def test_setup_allows_first_then_429s_immediately() -> None:
    """1 POST to /setup succeeds; the 2nd returns 429 (FR-023).
    Setup is the bootstrap-once endpoint; back-to-back attempts
    are almost certainly an attacker probing."""
    app = _build_app(setup_limit=1)
    with TestClient(app) as client:
        first = client.post("/api/v3/auth/setup")
        assert first.status_code == 200
        second = client.post("/api/v3/auth/setup")
        assert second.status_code == 429


# ---------------------------------------------------------------------------
# T026 — default: 100/min per API key (or session)
# ---------------------------------------------------------------------------


def test_default_allows_first_100_then_429s_for_same_apikey() -> None:
    """100 GETs with the same X-Api-Key succeed; the 101st
    returns 429 (FR-024)."""
    app = _build_app(default_limit=100)
    with TestClient(app) as client:
        for _ in range(100):
            assert client.get(
                "/api/v3/anything",
                headers={"X-Api-Key": "rmk_a"},
            ).status_code == 200
        assert client.get(
            "/api/v3/anything",
            headers={"X-Api-Key": "rmk_a"},
        ).status_code == 429


def test_default_keyed_per_apikey_not_shared() -> None:
    """Different API keys get separate buckets — multiple
    operators sharing a host don't share a single budget."""
    app = _build_app(default_limit=2)
    with TestClient(app) as client:
        for _ in range(2):
            assert client.get(
                "/api/v3/anything",
                headers={"X-Api-Key": "rmk_a"},
            ).status_code == 200
        assert client.get(
            "/api/v3/anything",
            headers={"X-Api-Key": "rmk_a"},
        ).status_code == 429
        # Different key — fresh budget.
        assert client.get(
            "/api/v3/anything",
            headers={"X-Api-Key": "rmk_b"},
        ).status_code == 200


def test_default_falls_back_to_session_cookie_when_no_apikey() -> None:
    """Cookie-session callers are keyed by the session value.
    Same session = same bucket."""
    app = _build_app(default_limit=2)
    with TestClient(app) as client:
        client.cookies.set("session", "shared-session")
        for _ in range(2):
            assert client.get("/api/v3/anything").status_code == 200
        assert client.get("/api/v3/anything").status_code == 429


# ---------------------------------------------------------------------------
# T027 — /api/v3/health is exempt
# ---------------------------------------------------------------------------


def test_health_endpoint_exempt_from_rate_limit() -> None:
    """Cluster orchestrators / uptime probes hit /health every
    few seconds; they MUST NOT be rate-limited (FR-001a)."""
    app = _build_app(default_limit=2)
    with TestClient(app) as client:
        # 50 calls — well past any default limit.
        for _ in range(50):
            assert client.get("/api/v3/health").status_code == 200


# ---------------------------------------------------------------------------
# Disabled flag is a no-op
# ---------------------------------------------------------------------------


def test_disabled_middleware_passes_everything_through() -> None:
    """``enabled=False`` makes the middleware a no-op — the
    default at boot until ROMARR_RATE_LIMIT_ENABLED=true."""
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        enabled=False,
        login_limit=1,
    )

    @app.post("/api/v3/auth/login")
    async def login() -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app) as client:
        for _ in range(20):
            assert client.post("/api/v3/auth/login").status_code == 200


# ---------------------------------------------------------------------------
# Retry-After header decreases as the window ages
# ---------------------------------------------------------------------------


def test_retry_after_header_reflects_window_age() -> None:
    """Once over the limit, the Retry-After header tells the
    client when the oldest in-window request ages out. As the
    clock advances, Retry-After shrinks accordingly."""
    clock = _Clock()
    app = _build_app(login_limit=1, clock=clock)
    with TestClient(app) as client:
        assert client.post("/api/v3/auth/login").status_code == 200

        # Hit at t=0 + a tiny epsilon → Retry-After ≈ 60s.
        first_429 = client.post("/api/v3/auth/login")
        assert first_429.status_code == 429
        first_retry = int(first_429.headers["retry-after"])

        # Advance 30s — the same blocked call now has ~30s left.
        clock.advance(30)
        second_429 = client.post("/api/v3/auth/login")
        assert second_429.status_code == 429
        second_retry = int(second_429.headers["retry-after"])
        assert second_retry < first_retry
