"""WIRE phase audit (T081, T082, T083, FR-001/004/005).

Tests at this level catch drift across every router we ship.
A new endpoint that forgets to declare ``require_role`` or
slips into the public surface unintentionally trips one of
these assertions.

The "public set" is a documented allow-list of routes that
intentionally don't require authentication:

  * the root probe and the OpenAPI docs URLs;
  * the auth bootstrap path (setup / login / logout);
  * the importer download-complete webhook (gated by its own
    bearer token, not the auth chain);
  * the notification webhook-payloads doc (public reference);
  * the auth-tiered probes (``system/status``, ``health``)
    that call ``get_current_principal`` directly so they can
    return a public-tier shape when no principal resolves.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from romarr.api import create_app
from romarr.api.dependencies import (
    get_current_principal,
    require_admin,
    require_readonly,
    require_user,
)

# Routes that do NOT require authentication — explicit allow-list.
PUBLIC_PATHS: set[str] = {
    "/",
    # FastAPI built-ins — no auth on the docs URLs.
    "/api/v3/docs",
    "/api/v3/redoc",
    "/api/v3/openapi.json",
    "/api/v3/docs/oauth2-redirect",
    # Auth bootstrap.
    "/api/v3/auth/setup",
    "/api/v3/auth/login",
    "/api/v3/auth/logout",
    # Importer webhook — gated by its own bearer token, not the
    # auth chain. See spec 008.
    "/api/v3/webhook/download-complete",
    # Public reference doc.
    "/api/v3/notification/webhook-payloads.md",
}

# Routes that tier the response by auth — they call
# ``get_current_principal`` directly rather than gating with
# ``require_role`` so unauthenticated callers receive the public
# shape. Tracked separately so T082 doesn't flag them as
# "missing require_role".
TIERED_PATHS: set[str] = {
    "/api/v3/system/status",
    "/api/v3/health",
}

ROLE_GUARDS = {require_admin, require_user, require_readonly}


def _all_routes(app: pytest.FixtureRequest | None = None) -> list[APIRoute]:
    """Snapshot every APIRoute on a freshly-built app."""
    fresh_app = create_app()
    return [r for r in fresh_app.routes if isinstance(r, APIRoute)]


def _has_dependency(route: APIRoute, callable_: object) -> bool:
    """Recurse through ``route.dependant`` looking for the given
    callable. ``Depends(...)`` chains nest arbitrarily; this
    walks the whole tree."""
    seen: set[int] = set()

    def _walk(dep: object) -> bool:
        if id(dep) in seen:
            return False
        seen.add(id(dep))
        if getattr(dep, "call", None) is callable_:
            return True
        return any(_walk(sub) for sub in getattr(dep, "dependencies", []))

    return _walk(route.dependant)


def _has_any_auth_in_tree(route: APIRoute) -> bool:
    """True iff any auth dependency (require_role or
    get_current_principal) is anywhere in the route's
    dependency tree."""
    return any(
        _has_dependency(route, dep)
        for dep in (
            *ROLE_GUARDS,
            get_current_principal,
        )
    )


def _has_role_guard(route: APIRoute) -> bool:
    """True iff one of the three documented role guards is
    in the route's dependency tree."""
    return any(_has_dependency(route, guard) for guard in ROLE_GUARDS)


# ---------------------------------------------------------------------------
# T083 — route count floor (FR-001 target ≥ 90)
# ---------------------------------------------------------------------------


# FR-001 mandates ≥ 90 distinct routes at spec-013 completion.
# As of slice 34 (log router shipped) the count is 95, past
# the target. The floor below catches accidental endpoint
# removal — raise it as more endpoints land.
_FR_001_TARGET = 90


def test_route_count_meets_fr_001_target() -> None:
    """FR-001: the unified API surface has at least 90 distinct
    routes. Catches drift in either direction — accidental
    endpoint removal trips this gate."""
    routes = _all_routes()
    distinct_paths = {r.path for r in routes}
    assert len(distinct_paths) >= _FR_001_TARGET, (
        f"only {len(distinct_paths)} distinct routes — "
        f"FR-001 requires ≥ {_FR_001_TARGET}"
    )


# ---------------------------------------------------------------------------
# T081 — every non-public route requires authentication
# ---------------------------------------------------------------------------


def test_every_non_public_route_requires_authentication() -> None:
    """Every route NOT in the public allow-list must reach
    ``require_admin`` / ``require_user`` / ``require_readonly``
    OR call ``get_current_principal`` directly (the auth-tiered
    pattern)."""
    missing: list[str] = []
    for route in _all_routes():
        if route.path in PUBLIC_PATHS:
            continue
        if _has_any_auth_in_tree(route):
            continue
        missing.append(f"{sorted(route.methods - {'HEAD'})} {route.path}")

    assert missing == [], (
        "Routes without any auth dependency (and not in the "
        "public allow-list):\n  " + "\n  ".join(missing)
    )


# ---------------------------------------------------------------------------
# T082 — every non-public, non-tiered route declares a role guard
# ---------------------------------------------------------------------------


def test_every_protected_route_declares_a_role_guard() -> None:
    """Routes that aren't public and aren't auth-tiered MUST
    declare one of ``require_admin`` / ``require_user`` /
    ``require_readonly`` (FR-005). Routes that tier the response
    via ``get_current_principal`` are tracked in TIERED_PATHS."""
    missing: list[str] = []
    for route in _all_routes():
        if route.path in PUBLIC_PATHS or route.path in TIERED_PATHS:
            continue
        if _has_role_guard(route):
            continue
        missing.append(f"{sorted(route.methods - {'HEAD'})} {route.path}")

    assert missing == [], (
        "Routes without an explicit role guard "
        "(require_admin / require_user / require_readonly):\n  "
        + "\n  ".join(missing)
    )


# ---------------------------------------------------------------------------
# Sanity: the public set actually exists in the wired app —
# typos in PUBLIC_PATHS would silently grow the allow-list.
# ---------------------------------------------------------------------------


def test_public_paths_are_real_routes() -> None:
    """Every entry in ``PUBLIC_PATHS`` must correspond to a
    route that actually exists. A typo or removed endpoint
    would otherwise pass through the audit silently."""
    actual = {r.path for r in _all_routes()}
    # FastAPI's built-in docs aren't APIRoutes — exclude them.
    builtin_docs = {
        "/api/v3/docs",
        "/api/v3/redoc",
        "/api/v3/openapi.json",
        "/api/v3/docs/oauth2-redirect",
    }
    declared = PUBLIC_PATHS - builtin_docs
    missing = declared - actual
    assert missing == set(), (
        f"PUBLIC_PATHS lists routes that don't exist on the app: "
        f"{sorted(missing)}"
    )


def test_tiered_paths_are_real_routes() -> None:
    """Every entry in ``TIERED_PATHS`` must correspond to a real
    route."""
    actual = {r.path for r in _all_routes()}
    missing = TIERED_PATHS - actual
    assert missing == set(), (
        f"TIERED_PATHS lists routes that don't exist on the app: "
        f"{sorted(missing)}"
    )
