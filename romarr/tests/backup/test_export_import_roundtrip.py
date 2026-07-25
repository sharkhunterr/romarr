"""Sanity tests — /api/v3/backup/{manifest,export,import}.

Round-trips a QualityProfile through the export → import cycle
to prove the wiring holds end-to-end.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password
from romarr.profiles.models import QualityProfile


async def _seed_admin_and_login(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="admin",
                role=ROLE_ADMIN,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()
    r = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "admin", "password": "goodpassword"},
    )
    assert r.status_code == 204


async def _seed_quality_profile(api_engine: AsyncEngine, name: str) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            QualityProfile(
                name=name,
                allowed_formats=["chd"],
                preferred_format="chd",
                require_dat_verified=False,
                allow_archive_double_compression=False,
                upgrade_until_format="chd",
                auto_grab_min_score=0,
                seed_key=None,
                is_user_modified=True,
                is_factory_default=False,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_manifest_returns_all_registered_handlers(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)

    r = await api_client.get("/api/v3/backup/manifest")
    assert r.status_code == 200
    payload = r.json()
    keys = {e["key"] for e in payload["resources"]}
    # 11 registered handlers
    assert {
        "dat_sources",
        "quality_profiles",
        "region_profiles",
        "dump_profiles",
        "language_profiles",
        "naming_profiles",
        "custom_formats",
        "download_clients",
        "indexers",
        "notifications",
        "platform_packs",
    } <= keys


@pytest.mark.asyncio
async def test_export_then_import_upsert_updates_counts(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await _seed_admin_and_login(api_engine, api_client)
    await _seed_quality_profile(api_engine, "roundtrip-test")

    # Export just quality_profiles
    r = await api_client.post(
        "/api/v3/backup/export",
        json={"resources": ["quality_profiles"], "include_secrets": False},
    )
    assert r.status_code == 200, r.text
    bundle: dict[str, Any] = r.json()
    assert "quality_profiles" in bundle["resources"]
    exported = bundle["resources"]["quality_profiles"]
    assert any(item.get("name") == "roundtrip-test" for item in exported)

    # Round-trip via upsert — should update (not duplicate)
    r = await api_client.post(
        "/api/v3/backup/import",
        json={
            "bundle": bundle,
            "resources": ["quality_profiles"],
            "mode": "upsert",
        },
    )
    assert r.status_code == 200, r.text
    outcome = next(
        o for o in r.json()["outcomes"] if o["key"] == "quality_profiles"
    )
    # Existing row was updated, not duplicated
    assert outcome["updated"] >= 1
    assert outcome["created"] == 0

    # Verify still only one row of that name
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows = (
            (
                await session.execute(
                    select(QualityProfile).where(
                        QualityProfile.name == "roundtrip-test"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_manifest_requires_admin(api_client: httpx.AsyncClient) -> None:
    r = await api_client.get("/api/v3/backup/manifest")
    assert r.status_code == 401
