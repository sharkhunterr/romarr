"""Canonical 401 envelope smoke test (spec 010 T089, FR-023).

The spec mandates that NO 401 response body discloses which auth
method failed. Every InvalidCredentials / SessionExpired /
SessionNotFound / ApiKeyInvalid / ApiKeyExpired / ApiKeyRevoked
exception MUST surface the same envelope. This test fires one
unauthenticated request per known-protected endpoint and pins
the body shape so a future error-handler refactor can't leak
method-specific text.

Implementation note: the envelope is
``{"errorMessage": "unauthenticated", "errorCode": "unauthenticated"}``
plus a ``WWW-Authenticate: Cookie`` header. The spec's older
``{"detail": "unauthenticated"}`` shape is the FastAPI default;
Romarr ships the Sonarr-compatible envelope instead so existing
tooling (Notifiarr, Recyclarr, Homepage) consumes the body
without special-casing.
"""

from __future__ import annotations

import httpx
import pytest


_PROTECTED_PATHS: tuple[tuple[str, str], ...] = (
    ("GET", "/api/v3/auth/me"),
    ("GET", "/api/v3/user"),
    ("POST", "/api/v3/auth/api-key"),
    ("GET", "/api/v3/rom/library"),
    ("GET", "/api/v3/qualityprofile"),
    ("GET", "/api/v3/rom/regionprofile"),
    ("GET", "/api/v3/indexer"),
    ("GET", "/api/v3/downloadclient"),
    ("GET", "/api/v3/notification"),
    ("GET", "/api/v3/system/tasks"),
    ("GET", "/api/v3/queue"),
    ("GET", "/api/v3/wanted/missing"),
    ("GET", "/api/v3/calendar"),
    ("GET", "/api/v3/system/backup"),
)


@pytest.mark.parametrize(
    ("method", "path"), _PROTECTED_PATHS
)
@pytest.mark.asyncio
async def test_unauthenticated_returns_canonical_envelope(
    api_client: httpx.AsyncClient, method: str, path: str
) -> None:
    """Every protected endpoint returns the same 401 body
    shape. No method-specific leaks (e.g. "session expired" vs
    "api key invalid")."""
    response = await api_client.request(method, path)
    assert response.status_code == 401, (
        f"{method} {path} returned {response.status_code}, "
        f"expected 401: {response.text}"
    )
    body = response.json()
    assert body == {
        "errorMessage": "unauthenticated",
        "errorCode": "unauthenticated",
    }, f"{method} {path} body diverges from canonical envelope: {body}"


@pytest.mark.asyncio
async def test_unauthenticated_body_does_not_leak_method(
    api_client: httpx.AsyncClient,
) -> None:
    """No keyword in the 401 body identifies which auth
    method (cookie / api-key / proxy / OIDC) was attempted.
    Catches a regression where a refactor accidentally
    plumbs the underlying exception's message through."""
    response = await api_client.get("/api/v3/auth/me")
    assert response.status_code == 401
    text = response.text.lower()
    forbidden_keywords = (
        "session",
        "cookie",
        "api key",
        "apikey",
        "bearer",
        "jwt",
        "expired",
        "revoked",
        "credentials",
        "deactivated",
    )
    for keyword in forbidden_keywords:
        assert keyword not in text, (
            f"401 body must not leak {keyword!r}: {response.text}"
        )
