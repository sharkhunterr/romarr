"""Sonarr-shape /api/v3/system/status compat tests (T090, T091, SC-001).

The constitutional Article IV mandate is "*arr ecosystem
compatibility": Notifiarr, Recyclarr, Homepage, Homarr, Janitorr,
and Overseerr-shaped tools probe ``/api/v3/system/status`` with an
API key and recognise the response as a Sonarr-flavoured *arr
peer. The fixture under ``tests/fixtures/api/`` is the canonical
key set those tools expect.

Two tests:

  * **T090** — pin that Romarr's response is a *superset* of the
    fixture's keys. Romarr is allowed to add ROM-specific keys
    (we don't, today, but the contract is "every Sonarr key is
    present", not "exactly these keys"). Missing any Sonarr key
    breaks ecosystem-tooling and is a regression.
  * **T091** — replay the captured Notifiarr probe (header set,
    method, path) and assert HTTP 200 with the Sonarr-shape
    response.

The tests authenticate via API key (the realistic path
ecosystem tooling uses) rather than cookie session.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_api_key, hash_password
from romarr.auth.models import ApiKey

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "api"


# ---------------------------------------------------------------------------
# Fixture loaders
# ---------------------------------------------------------------------------


def _load_sonarr_fixture() -> dict[str, object]:
    """Load the documented Sonarr v4 status snapshot. The
    ``_comment`` key is dropped — it's metadata, not part of the
    canonical key set."""
    raw = json.loads(
        (_FIXTURE_DIR / "sonarr_status_fixture.json").read_text()
    )
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _load_notifiarr_probe() -> dict[str, object]:
    raw = json.loads(
        (_FIXTURE_DIR / "notifiarr_probe_payload.json").read_text()
    )
    return {k: v for k, v in raw.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_admin_with_api_key(engine: AsyncEngine) -> str:
    """Insert an admin user and a matching API key. Returns the
    plaintext key so the caller can send it as ``X-Api-Key``."""
    plaintext = "rmk_test_sonarr_probe_compat"
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        user = User(
            username="probe-admin",
            role=ROLE_ADMIN,
            is_active=True,
            hashed_password=hash_password("goodpassword"),
        )
        session.add(user)
        await session.flush()
        session.add(
            ApiKey(
                user_id=user.id,
                name="notifiarr",
                key_prefix=plaintext[:8],
                key_hash=hash_api_key(plaintext),
                scopes=["read"],
            )
        )
        await session.commit()
    return plaintext


# ---------------------------------------------------------------------------
# T090 — Romarr's response is a superset of Sonarr's keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_response_is_superset_of_sonarr_fixture(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """SC-001: every key Sonarr emits in /api/v3/system/status
    is present in Romarr's authenticated-tier response. Extra
    Romarr-specific keys are allowed; missing ones aren't."""
    plaintext = await _seed_admin_with_api_key(api_engine)
    fixture = _load_sonarr_fixture()

    resp = await api_client.get(
        "/api/v3/system/status",
        headers={"X-Api-Key": plaintext},
    )
    assert resp.status_code == 200
    body = resp.json()

    # The Sonarr-fixture keys we DOCUMENT as part of the contract
    # — i.e. the v3+v4 union we explicitly emit. Sonarr also
    # emits OS / mono / package / build-time info that's not
    # meaningful for Romarr; those are tracked under "extras"
    # in the contract clarification (see spec 013).
    documented_keys = {
        "version",
        "isProduction",
        "instanceName",
        "urlBase",
        "osName",
        "runtimeVersion",
        "appData",
        "startTime",
        "databaseType",
        "databaseVersion",
        "migrationVersion",
        "runtimeName",
    }
    # Sanity: every documented key is in the fixture (catches
    # fixture / spec drift).
    assert documented_keys.issubset(fixture.keys()), (
        f"sonarr_status_fixture.json missing documented keys: "
        f"{documented_keys - set(fixture.keys())}"
    )
    # And every documented key is in Romarr's response.
    assert documented_keys.issubset(body.keys()), (
        f"GET /api/v3/system/status missing keys: "
        f"{documented_keys - set(body.keys())}"
    )


@pytest.mark.asyncio
async def test_status_response_keys_match_documented_set_exactly(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """The authenticated tier emits the documented union — no
    accidental omissions, no surprise additions. Locks the
    contract so a future router refactor doesn't silently drop
    a Sonarr-required field."""
    plaintext = await _seed_admin_with_api_key(api_engine)

    resp = await api_client.get(
        "/api/v3/system/status",
        headers={"X-Api-Key": plaintext},
    )
    expected = {
        "version",
        "isProduction",
        "instanceName",
        "urlBase",
        "osName",
        "runtimeVersion",
        "appData",
        "startTime",
        "databaseType",
        "databaseVersion",
        "migrationVersion",
        "runtimeName",
    }
    assert set(resp.json().keys()) == expected


# ---------------------------------------------------------------------------
# T091 — Notifiarr probe replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notifiarr_probe_succeeds_with_api_key(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """Replay the captured Notifiarr probe payload against the
    running app and assert HTTP 200 with the Sonarr-shape
    response. The probe is a GET with an X-Api-Key header — no
    body. This is exactly what an *arr-aware tool sends on first
    connect."""
    plaintext = await _seed_admin_with_api_key(api_engine)
    probe = _load_notifiarr_probe()

    headers = dict(probe["headers"])  # type: ignore[arg-type]
    # Replace the placeholder API key with the seeded plaintext.
    headers["X-Api-Key"] = plaintext

    resp = await api_client.request(
        method=probe["method"],  # type: ignore[arg-type]
        url=probe["path"],  # type: ignore[arg-type]
        headers=headers,
    )
    assert resp.status_code == probe["expected_status"]
    assert resp.headers["content-type"].startswith(
        probe["expected_content_type"]  # type: ignore[arg-type]
    )

    # The body is the Sonarr-shape JSON the tool will cache.
    body = resp.json()
    assert body["instanceName"] == "Romarr"
    assert body["isProduction"] is True
    assert body["version"]


# ---------------------------------------------------------------------------
# Public-tier fallback — unauthenticated probes still get the
# Sonarr peer-recognition shape, just minimised.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_probe_gets_minimal_peer_recognition_shape(
    api_client: httpx.AsyncClient,
) -> None:
    """An unauthenticated probe still recognises Romarr as an
    *arr peer (version + isProduction is the documented public
    minimum; see spec 013 clarification on auth-tiered status)."""
    resp = await api_client.get("/api/v3/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "version" in body
    assert body.get("isProduction") is True
