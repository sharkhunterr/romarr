"""Pack-lifecycle endpoint tests (T045-T051)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.platform_packs.api.conftest import seed_admin_and_login


@pytest.mark.asyncio
async def test_upload_unauthenticated_returns_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", b"pack_version: '2026.04.001'", "text/yaml")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_valid_pack_applies(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T045: a multipart upload of a valid YAML applies the pack and
    returns a ``PackUploadResult`` with action='applied'."""
    await seed_admin_and_login(api_engine, api_client)

    body = pack_yaml("valid/minimal.yaml")
    response = await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", body, "text/yaml")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "applied"
    assert payload["pack_version"] == "2026.04.001"
    diff = payload["diff"]
    assert any(d["slug"] == "megadrive" and d["action"] == "inserted" for d in diff)


@pytest.mark.asyncio
async def test_upload_bad_yaml_returns_400(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T046: malformed YAML → HTTP 400 with parse-error details."""
    await seed_admin_and_login(api_engine, api_client)

    response = await api_client.post(
        "/api/v3/rom/platform-pack",
        files={
            "file": (
                "pack.yaml",
                pack_yaml("invalid_yaml/truncated.yaml"),
                "text/yaml",
            )
        },
    )
    assert response.status_code == 400
    detail = response.json()
    assert detail["errorCode"] == "validation_failed"


@pytest.mark.asyncio
async def test_upload_schema_violation_returns_400_with_path(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T047: missing pack_version → HTTP 400 with the JSON path of the violation."""
    await seed_admin_and_login(api_engine, api_client)

    response = await api_client.post(
        "/api/v3/rom/platform-pack",
        files={
            "file": (
                "pack.yaml",
                pack_yaml("invalid_schema/missing_pack_version.yaml"),
                "text/yaml",
            )
        },
    )
    assert response.status_code == 400
    detail = response.json()
    paths = {d["path"] for d in detail["details"]}
    # Either the root violation (pack_version is a required key) or the
    # explicit /pack_version path.
    assert paths and ("/" in paths or any("pack_version" in p for p in paths))


@pytest.mark.asyncio
async def test_upload_cycle_returns_400_naming_cycle(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T048: parent_platform_slug cycle → HTTP 400 with the cycle named."""
    await seed_admin_and_login(api_engine, api_client)

    response = await api_client.post(
        "/api/v3/rom/platform-pack",
        files={
            "file": (
                "pack.yaml",
                pack_yaml("invalid_refs/parent_cycle_a_b.yaml"),
                "text/yaml",
            )
        },
    )
    assert response.status_code == 400
    detail = response.json()
    codes = {d["code"] for d in detail["details"]}
    assert "parent_cycle" in codes


@pytest.mark.asyncio
async def test_validate_only_does_not_write(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T049: ``/validate`` returns ``would_apply`` without touching the DB."""
    await seed_admin_and_login(api_engine, api_client)

    body = pack_yaml("valid/minimal.yaml")
    response = await api_client.post(
        "/api/v3/rom/platform-pack/validate",
        files={"file": ("pack.yaml", body, "text/yaml")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "would_apply"
    assert payload["database_state_unchanged"] is True

    # No platform_pack rows persisted — list endpoint stays empty.
    list_response = await api_client.get("/api/v3/rom/platform-pack")
    assert list_response.status_code == 200
    assert list_response.json() == []


@pytest.mark.asyncio
async def test_list_orders_most_recent_first(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T050: GET /platform-pack lists every pack, most-recent first."""
    await seed_admin_and_login(api_engine, api_client)

    # First pack.
    await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", pack_yaml("valid/minimal.yaml"), "text/yaml")},
    )

    # Second pack with a different version + slug.
    second_body = (
        b"pack_version: '2026.05.002'\n"
        b"schema_version: 1\n"
        b"description: 'second pack'\n"
        b"platforms:\n"
        b"  - slug: snes\n    name: SNES\n    manufacturer: Nintendo\n"
        b"    formats:\n      - extension: '.sfc'\n        format_type: cartridge\n"
    )
    await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", second_body, "text/yaml")},
    )

    response = await api_client.get("/api/v3/rom/platform-pack")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    versions = [r["pack_version"] for r in rows]
    # Most-recent applied_at first.
    assert versions[0] == "2026.05.002"
    assert versions[1] == "2026.04.001"


@pytest.mark.asyncio
async def test_detail_returns_pack_and_audit_history(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    await seed_admin_and_login(api_engine, api_client)

    body = pack_yaml("valid/minimal.yaml")
    await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", body, "text/yaml")},
    )
    # Re-upload to get a `skipped` audit row.
    await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", body, "text/yaml")},
    )

    response = await api_client.get("/api/v3/rom/platform-pack/2026.04.001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["pack_version"] == "2026.04.001"
    actions = [h["action"] for h in payload["history"]]
    assert "applied" in actions
    assert "skipped" in actions


@pytest.mark.asyncio
async def test_detail_unknown_returns_404(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.get("/api/v3/rom/platform-pack/9999.99.999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reapply_endpoint_documents_v1_deferral(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """T051 (v1+ deferral): reapply by reference is documented as 501
    until the pack body is persisted in a follow-up slice."""
    await seed_admin_and_login(api_engine, api_client)
    await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", pack_yaml("valid/minimal.yaml"), "text/yaml")},
    )
    response = await api_client.post(
        "/api/v3/rom/platform-pack/2026.04.001/apply"
    )
    assert response.status_code == 501
    detail = response.json()
    assert detail["errorCode"] == "not_implemented"


@pytest.mark.asyncio
async def test_validate_only_reports_would_skip_for_known_pack(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    pack_yaml: Callable[[str], bytes],
) -> None:
    """The validate-only endpoint flags a re-upload of an already-applied
    body as ``would_skip`` so the operator UI can present "this is a
    no-op, stop wasting your time" before opening a write connection."""
    await seed_admin_and_login(api_engine, api_client)
    body = pack_yaml("valid/minimal.yaml")
    await api_client.post(
        "/api/v3/rom/platform-pack",
        files={"file": ("pack.yaml", body, "text/yaml")},
    )

    response = await api_client.post(
        "/api/v3/rom/platform-pack/validate",
        files={"file": ("pack.yaml", body, "text/yaml")},
    )
    assert response.status_code == 200
    assert response.json()["action"] == "would_skip"
