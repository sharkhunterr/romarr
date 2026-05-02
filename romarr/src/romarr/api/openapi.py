"""OpenAPI 3.1 customisation (T080, FR-013/014/015).

FastAPI auto-generates a complete OpenAPI document from the
route signatures and Pydantic schemas. The defaults are good
but two changes matter for spec 013:

  * **OpenAPI version** — FastAPI defaults to 3.0.x; the spec
    mandates 3.1.0 (FR-013, SC-002). Bumping the version
    enables ``examples`` arrays and the ``null`` type properly.
  * **Security schemes** — the FastAPI default emits one scheme
    per dependency; Romarr advertises four equivalent auth
    paths (FR-015) — API key in header, API key as query param,
    cookie session, bearer JWT. Documenting all four lets
    operators see at a glance which methods their API keys can
    use.

The :func:`customize_openapi` helper installs a ``custom_openapi``
function on the FastAPI app that:

  1. caches the result on ``app.openapi_schema`` (FastAPI's
     standard cache hook);
  2. forces ``openapi.openapi = "3.1.0"``;
  3. injects the four documented security schemes under
     ``components.securitySchemes`` and ``security``;
  4. ensures every operation carries a ``tags`` array — Sonarr
     tooling groups by tag so a missing tag silently breaks
     navigation. Operations without an explicit tag get the
     fallback ``"Misc"`` tag rather than raising at startup
     (kept lenient so a third-party plugin router doesn't
     brick the app).

The router-level work that goes alongside this — adding examples
to specific endpoints (FR-014) — is handled where the route lives
rather than centrally; this module only customises the
auto-generated document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.openapi.utils import get_openapi

if TYPE_CHECKING:
    from fastapi import FastAPI


_FALLBACK_TAG = "Misc"


_SECURITY_SCHEMES: dict[str, dict[str, Any]] = {
    "ApiKeyHeader": {
        "type": "apiKey",
        "name": "X-Api-Key",
        "in": "header",
        "description": (
            "Per-user API key issued via "
            "POST /api/v3/auth/api-key. Sent as the X-Api-Key "
            "header. Compatible with Notifiarr / Recyclarr / "
            "Homepage."
        ),
    },
    "ApiKeyQuery": {
        "type": "apiKey",
        "name": "apikey",
        "in": "query",
        "description": (
            "Same key as ApiKeyHeader, transported in the URL "
            "query string for tools that can't add headers."
        ),
    },
    "CookieSession": {
        "type": "apiKey",
        "name": "session",
        "in": "cookie",
        "description": (
            "Browser cookie session established via "
            "POST /api/v3/auth/login. Used by the Romarr UI."
        ),
    },
    "BearerJwt": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "OIDC-issued JWT in the standard "
            "``Authorization: Bearer <token>`` header. Used for "
            "SSO callers."
        ),
    },
}


def _ensure_tags(operation: dict[str, Any]) -> None:
    """Mutate ``operation`` in place so it has a non-empty
    ``tags`` array. Lenient by default — missing tags get the
    fallback rather than raising."""
    tags = operation.get("tags")
    if not tags:
        operation["tags"] = [_FALLBACK_TAG]


def customize_openapi(app: FastAPI) -> None:
    """Install the spec-013 customisation on ``app``.

    Idempotent — calling twice replaces the cached schema with
    a regenerated one. Tests that mutate routes after build
    should call ``app.openapi_schema = None`` between calls to
    invalidate the cache."""

    def _build_schema() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version="3.1.0",
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
            servers=app.servers,
        )

        # Security schemes (FR-015).
        components = schema.setdefault("components", {})
        components.setdefault(
            "securitySchemes", {}
        ).update(_SECURITY_SCHEMES)
        # Top-level ``security`` advertises that any of the four
        # is acceptable. Per-route security can still override.
        schema.setdefault(
            "security",
            [
                {"ApiKeyHeader": []},
                {"ApiKeyQuery": []},
                {"CookieSession": []},
                {"BearerJwt": []},
            ],
        )

        # Tag enforcement (FR-014).
        for path_item in schema.get("paths", {}).values():
            for method in (
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "options",
                "head",
            ):
                operation = path_item.get(method)
                if isinstance(operation, dict):
                    _ensure_tags(operation)

        app.openapi_schema = schema
        return schema

    app.openapi = _build_schema  # type: ignore[method-assign]


__all__ = ["customize_openapi"]
