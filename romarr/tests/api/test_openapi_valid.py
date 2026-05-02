"""OpenAPI customisation tests (T075, T076, T078, T079).

The customizer in :mod:`romarr.api.openapi` mutates the
auto-generated FastAPI schema to:
  * force OpenAPI 3.1.0 (T075, FR-013, SC-002);
  * inject the four documented security schemes (T078, FR-015);
  * ensure every operation has a tag (T079, FR-014);
  * keep operationIds unique across the whole app (T076,
    FR-013).

T077 (per-endpoint examples) is handled at the route level —
each ``@router.post(...)`` carries its own ``examples=[...]``
when the spec demands them. Skipped from this slice; tracked as
a follow-up under T077.
"""

from __future__ import annotations

import pytest
from openapi_spec_validator import validate

from romarr.api import create_app

# ---------------------------------------------------------------------------
# T075 — validates against OpenAPI 3.1
# ---------------------------------------------------------------------------


def test_openapi_version_is_3_1_0() -> None:
    """``openapi`` field is exactly ``3.1.0`` per FR-013."""
    app = create_app()
    schema = app.openapi()
    assert schema["openapi"] == "3.1.0"


def test_openapi_validates_against_3_1_schema() -> None:
    """Pass the schema through the official validator with the
    3.1 dispatcher pinned. Any structural error fails the test."""
    app = create_app()
    schema = app.openapi()
    # ``validate`` raises on error. The validator dispatches to
    # the right OpenAPI version based on the schema's ``openapi``
    # field — 3.1.0 here, so the 3.1 validator runs.
    validate(schema)


# ---------------------------------------------------------------------------
# T076 — every endpoint has a unique operationId
# ---------------------------------------------------------------------------


def test_operation_ids_are_unique() -> None:
    """FastAPI auto-generates operationIds from the function
    name + path. If two routes happen to share both, the IDs
    collide. This test catches that drift early."""
    app = create_app()
    schema = app.openapi()

    seen: set[str] = set()
    duplicates: list[str] = []
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
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId")
            if op_id is None:
                continue
            if op_id in seen:
                duplicates.append(op_id)
            seen.add(op_id)

    assert duplicates == [], f"duplicate operationIds: {duplicates}"


# ---------------------------------------------------------------------------
# T078 — security schemes present
# ---------------------------------------------------------------------------


def test_security_schemes_advertise_all_four_methods() -> None:
    """FR-015: API-key-header, API-key-query, cookie session,
    bearer JWT — all four advertised under
    ``components.securitySchemes``."""
    app = create_app()
    schema = app.openapi()

    schemes = schema["components"]["securitySchemes"]
    assert "ApiKeyHeader" in schemes
    assert "ApiKeyQuery" in schemes
    assert "CookieSession" in schemes
    assert "BearerJwt" in schemes

    # Shape spot-checks on the most-used scheme.
    assert schemes["ApiKeyHeader"] == {
        "type": "apiKey",
        "name": "X-Api-Key",
        "in": "header",
        "description": (
            "Per-user API key issued via "
            "POST /api/v3/auth/api-key. Sent as the X-Api-Key "
            "header. Compatible with Notifiarr / Recyclarr / "
            "Homepage."
        ),
    }


def test_top_level_security_lists_alternatives() -> None:
    """The four schemes are advertised at the top level as
    OR-equivalent — any one is acceptable."""
    app = create_app()
    schema = app.openapi()
    expected = [
        {"ApiKeyHeader": []},
        {"ApiKeyQuery": []},
        {"CookieSession": []},
        {"BearerJwt": []},
    ]
    assert schema["security"] == expected


# ---------------------------------------------------------------------------
# T079 — every endpoint carries at least one tag
# ---------------------------------------------------------------------------


def test_every_operation_has_a_tag() -> None:
    """FR-014: every operation has a ``tags`` array. Operations
    without an explicit tag get the documented fallback ``Misc``
    rather than emitting an empty / missing array."""
    app = create_app()
    schema = app.openapi()

    for path, path_item in schema.get("paths", {}).items():
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
            if not isinstance(operation, dict):
                continue
            tags = operation.get("tags")
            assert tags, (
                f"operation {method.upper()} {path} has no tag — "
                f"customize_openapi should have applied the "
                f"fallback"
            )


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


def test_openapi_result_is_cached() -> None:
    """FastAPI caches via ``app.openapi_schema``. Calling
    ``app.openapi()`` twice should return the same dict instance
    on the second call."""
    app = create_app()
    first = app.openapi()
    second = app.openapi()
    assert first is second


# ---------------------------------------------------------------------------
# Smoke: the customizer is idempotent — re-running on a fresh app
# yields a stable shape.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("_", range(2))
def test_repeated_app_builds_produce_valid_3_1_spec(_: int) -> None:
    app = create_app()
    schema = app.openapi()
    validate(schema)
    assert schema["openapi"] == "3.1.0"
