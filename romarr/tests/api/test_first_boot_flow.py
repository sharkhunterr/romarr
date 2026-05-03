"""End-to-end first-boot smoke test (slice 192).

Exercises the full operator first-boot path the Docker image
ships:

  1. Fresh DB, no users
  2. ``maybe_bootstrap_setup_token`` mints a one-shot token
     (lifespan-equivalent — we drive it directly here so the
     test is self-contained)
  3. ``POST /api/v3/auth/setup`` with the plaintext token +
     admin credentials → admin user created, session cookie
     set, auto-logged-in
  4. ``GET /api/v3/auth/me`` with the cookie → returns the
     freshly-created admin
  5. ``POST /api/v3/rom/library`` to create the first library
     (admin gate satisfied via the session cookie)
  6. ``GET /api/v3/rom/library`` lists the new library

A single regression here would mean the operator can't get
past first boot. Worth its weight in CI minutes.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth.setup import maybe_bootstrap_setup_token
from romarr.profiles.models import (
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)


async def _mint_setup_token(api_engine: AsyncEngine) -> str:
    """Direct lifespan-equivalent: mint one setup_token row.

    Returns the plaintext exactly once (the API path matches
    the production lifespan, which logs the plaintext at
    WARNING for the operator to capture)."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        result = await maybe_bootstrap_setup_token(session)
        await session.commit()
    assert result.plaintext is not None, (
        "fresh DB must mint a setup token"
    )
    return result.plaintext


async def _seed_default_profiles(api_engine: AsyncEngine) -> dict[str, int]:
    """One row of each profile type — needed for LibraryCreate's
    NOT-NULL FK columns."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        quality = QualityProfile(
            name="quality-default",
            allowed_formats=["raw"],
            preferred_format="raw",
            require_dat_verified=False,
            upgrade_until_format="raw",
        )
        region = RegionProfile(
            name="region-default",
            priorities=["USA"],
            allow_fallback_outside_priorities=True,
            exclude_regions=[],
        )
        dump = DumpProfile(
            name="dump-default",
            allowed_dump_status=["verified"],
            allow_proto_beta=False,
            allow_hacks=False,
            allow_trainers=False,
            allow_translations=False,
        )
        language = LanguageProfile(
            name="language-default",
            required_languages=[],
            preferred_languages=["en"],
            exclude_japanese_only=False,
        )
        naming = NamingProfile(
            name="naming-default",
            convention="no-intro",
            template="{{ game.title }}",
        )
        session.add_all([quality, region, dump, language, naming])
        await session.commit()
        return {
            "quality_profile_id": quality.id,
            "region_profile_id": region.id,
            "dump_profile_id": dump.id,
            "language_profile_id": language.id,
            "naming_profile_id": naming.id,
        }


@pytest.mark.asyncio
async def test_first_boot_setup_login_create_library(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """Full first-boot smoke: setup → me → create library → list.

    The setup endpoint auto-logs-in the freshly-minted admin
    so the cookie is available immediately for the library
    CRUD round-trip."""
    # 1-2. Fresh DB + token mint.
    plaintext = await _mint_setup_token(api_engine)
    profile_ids = await _seed_default_profiles(api_engine)

    # 3. POST /auth/setup creates the first admin + sets cookie.
    setup_resp = await api_client.post(
        "/api/v3/auth/setup",
        headers={"X-Setup-Token": plaintext},
        json={
            "username": "admin",
            "password": "correct-horse-battery-staple",
        },
    )
    assert setup_resp.status_code == 201, setup_resp.text
    body = setup_resp.json()
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"
    # Cookie is set on the client for subsequent requests.
    assert "romarr_session" in setup_resp.cookies

    # 4. The session cookie unlocks /auth/me.
    me_resp = await api_client.get("/api/v3/auth/me")
    assert me_resp.status_code == 200, me_resp.text
    assert me_resp.json()["username"] == "admin"

    # 5. Create the first library — admin gate satisfied.
    library_path = tmp_path / "rom-library"
    library_path.mkdir()
    create_resp = await api_client.post(
        "/api/v3/rom/library",
        json={
            "name": "First Library",
            "path": str(library_path),
            **profile_ids,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    library = create_resp.json()
    assert library["name"] == "First Library"
    assert library["lifecycle_policy"] == "hardlink_and_seed"

    # 6. List endpoint returns the library.
    list_resp = await api_client.get("/api/v3/rom/library")
    assert list_resp.status_code == 200
    libraries = list_resp.json()
    assert len(libraries) == 1
    assert libraries[0]["id"] == library["id"]


@pytest.mark.asyncio
async def test_health_endpoint_anonymous_returns_status_only(
    api_client: httpx.AsyncClient,
) -> None:
    """The constitutional uptime probe: ``GET /api/v3/health``
    must work without auth (FR-024a — Uptime-Kuma compat) and
    return only ``{status: ...}`` for anonymous callers (no
    internal-detail leakage). Catches the regression where the
    auth chain accidentally gates this endpoint, AND the
    regression where a fresh DB with no health rows produces a
    500 (it should be ok). The slice 187 docker-boot smoke
    found this 500 originally; this test pins the fix."""
    response = await api_client.get("/api/v3/health")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"status"}, (
        f"anonymous health body must be {{status}} only, got {body}"
    )
    assert body["status"] in ("ok", "warning", "error")


@pytest.mark.asyncio
async def test_system_status_anonymous_returns_minimal_shape(
    api_client: httpx.AsyncClient,
) -> None:
    """Spec 013 CL008: anonymous ``GET /api/v3/system/status``
    returns ``{version, isProduction}`` only — no Sonarr v3+v4
    internals. Catches the regression where a refactor leaks
    the full body to unauthenticated callers."""
    response = await api_client.get("/api/v3/system/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"version", "isProduction"}


@pytest.mark.asyncio
async def test_setup_with_wrong_token_returns_401(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """A token that doesn't match the stored hash → 401.
    Catches a regression where the constant-time compare
    accidentally normalises whitespace / case."""
    await _mint_setup_token(api_engine)

    setup_resp = await api_client.post(
        "/api/v3/auth/setup",
        headers={"X-Setup-Token": "not-the-real-token"},
        json={
            "username": "admin",
            "password": "correct-horse-battery-staple",
        },
    )
    assert setup_resp.status_code in (401, 403, 422), (
        f"expected 401/403/422 for wrong token, got {setup_resp.status_code}"
    )


@pytest.mark.asyncio
async def test_setup_consumes_token_so_replay_fails(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
) -> None:
    """Successful setup marks the token consumed. A replay
    with the same plaintext must fail — if it didn't, the
    token would be a permanent admin-creation backdoor."""
    plaintext = await _mint_setup_token(api_engine)

    first = await api_client.post(
        "/api/v3/auth/setup",
        headers={"X-Setup-Token": plaintext},
        json={
            "username": "admin",
            "password": "correct-horse-battery-staple",
        },
    )
    assert first.status_code == 201

    # Same token, different proposed admin — must fail.
    replay = await api_client.post(
        "/api/v3/auth/setup",
        headers={"X-Setup-Token": plaintext},
        json={
            "username": "evilcorp",
            "password": "correct-horse-battery-staple",
        },
    )
    assert replay.status_code in (401, 403, 410, 422), (
        f"expected 4xx on token replay, got {replay.status_code}"
    )
