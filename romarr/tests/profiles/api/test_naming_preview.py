"""Naming-template preview endpoint (T063)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.profiles.api.conftest import seed_user_and_login

_VALID_PROFILE = {
    "name": "Preview profile",
    "convention": "no-intro",
    "template": "{{ Game.Title }} ({{ Release.Region }}).{{ Dump.Extension }}",
    "platform_subfolder": True,
    "replace_illegal_chars": True,
    "multi_disc_subfolder": True,
}


@pytest.mark.asyncio
async def test_preview_renders_synthetic_release(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    response = await api_client.post(
        "/api/v3/rom/namingprofile/preview",
        json={"profile": _VALID_PROFILE, "sample_release_id": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert "rendered" in body
    # Synthetic sample release ships USA / md extension.
    assert "(USA)" in body["rendered"]
    assert body["rendered"].endswith(".md")


@pytest.mark.asyncio
async def test_preview_with_bad_template_returns_400(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    bad = {**_VALID_PROFILE, "template": "{{ Game.Bogus }}"}
    response = await api_client.post(
        "/api/v3/rom/namingprofile/preview",
        json={"profile": bad, "sample_release_id": 0},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "template_invalid"


@pytest.mark.asyncio
async def test_preview_blocks_non_admin(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """FR-032a: preview endpoint is admin-only (it can probe arbitrary release IDs)."""
    await seed_user_and_login(api_engine, api_client, role="user")
    response = await api_client.post(
        "/api/v3/rom/namingprofile/preview",
        json={"profile": _VALID_PROFILE, "sample_release_id": 0},
    )
    assert response.status_code == 403
