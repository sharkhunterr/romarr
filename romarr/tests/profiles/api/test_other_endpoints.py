"""Smoke tests for the five non-Quality profile routers (T057-T061).

The CRUD pattern is shared via :func:`make_crud_router`, so we
exercise one happy-path round-trip per type rather than duplicating
the full Quality test sweep.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.profiles.api.conftest import seed_user_and_login

_REGION_PAYLOAD = {
    "name": "Region X",
    "priorities": ["USA"],
    "allow_fallback_outside_priorities": True,
    "exclude_regions": [],
}


_DUMP_PAYLOAD = {
    "name": "Dump X",
    "allowed_dump_status": ["verified"],
    "allow_proto_beta": False,
    "allow_hacks": False,
    "allow_trainers": False,
    "allow_translations": False,
    "prefer_revision": "latest",
}


_LANGUAGE_PAYLOAD = {
    "name": "Lang X",
    "required_languages": ["en"],
    "preferred_languages": ["en"],
    "exclude_japanese_only": True,
}


_NAMING_PAYLOAD = {
    "name": "Naming X",
    "convention": "no-intro",
    "template": "{{ Game.Title }}.{{ Dump.Extension }}",
    "platform_subfolder": True,
    "replace_illegal_chars": True,
    "multi_disc_subfolder": True,
}


_CUSTOM_FORMAT_PAYLOAD = {
    "name": "Custom Format X",
    "score": 50,
    "conditions": [
        {"field": "tags", "operator": "matches_regex", "values": r"\[!\]"}
    ],
}


@pytest.mark.parametrize(
    ("base_path", "payload"),
    [
        ("/api/v3/rom/regionprofile", _REGION_PAYLOAD),
        ("/api/v3/rom/dumpprofile", _DUMP_PAYLOAD),
        ("/api/v3/rom/languageprofile", _LANGUAGE_PAYLOAD),
        ("/api/v3/rom/namingprofile", _NAMING_PAYLOAD),
        ("/api/v3/customformat", _CUSTOM_FORMAT_PAYLOAD),
    ],
    ids=["region", "dump", "language", "naming", "custom_format"],
)
@pytest.mark.asyncio
async def test_each_router_full_round_trip(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    base_path: str,
    payload: dict[str, object],
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")

    create = await api_client.post(base_path, json=payload)
    assert create.status_code == 201, create.text
    row_id = create.json()["id"]

    listing = await api_client.get(base_path)
    assert listing.status_code == 200

    fetch = await api_client.get(f"{base_path}/{row_id}")
    assert fetch.status_code == 200

    update = await api_client.put(
        f"{base_path}/{row_id}", json={"name": "Renamed"}
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Renamed"

    delete = await api_client.delete(f"{base_path}/{row_id}")
    assert delete.status_code == 204


@pytest.mark.parametrize(
    "base_path",
    [
        "/api/v3/rom/regionprofile",
        "/api/v3/rom/dumpprofile",
        "/api/v3/rom/languageprofile",
        "/api/v3/rom/namingprofile",
        "/api/v3/customformat",
    ],
)
@pytest.mark.asyncio
async def test_each_router_schema_endpoint(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    base_path: str,
) -> None:
    await seed_user_and_login(api_engine, api_client, role="user")
    response = await api_client.get(f"{base_path}/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "object"
    assert "name" in body["properties"]


# ---------------------------------------------------------------------------
# Naming-specific: bad template at create returns 422 (Pydantic validator)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_naming_post_with_bad_template_returns_422(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    # An empty template — Pydantic's min_length=1 rejects.
    bad = {**_NAMING_PAYLOAD, "template": ""}
    response = await api_client.post("/api/v3/rom/namingprofile", json=bad)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Custom Format: invalid regex at POST returns 400 from RegexCompileError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_format_post_with_invalid_regex_returns_400(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_user_and_login(api_engine, api_client, role="admin")
    bad = {
        **_CUSTOM_FORMAT_PAYLOAD,
        "conditions": [
            {"field": "tags", "operator": "matches_regex", "values": "[invalid("}
        ],
    }
    response = await api_client.post("/api/v3/customformat", json=bad)
    assert response.status_code == 400
    body = response.json()
    assert body["errorCode"] == "profile_validation"
    assert "invalid regex" in body["details"]
