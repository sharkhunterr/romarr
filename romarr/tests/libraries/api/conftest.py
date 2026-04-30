"""Module-local fixtures for the libraries API tests.

Identical bootstrap to the profiles API conftest — patch the auth
secret, seed a user with the requested role, log in via the auth
router. Plus a helper that seeds the five profile rows the Library
table's NOT NULL FKs require.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, ROLE_USER, User, hash_password
from romarr.config.settings import get_settings
from romarr.profiles.models import (
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def seed_user_and_login(
    api_engine: AsyncEngine,
    api_client: httpx.AsyncClient,
    *,
    role: Literal["admin", "user"] = "admin",
) -> None:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    role_value = ROLE_ADMIN if role == "admin" else ROLE_USER
    async with sm() as session:
        session.add(
            User(
                username=f"{role}-user",
                role=role_value,
                is_active=True,
                hashed_password=hash_password("goodpassword"),
            )
        )
        await session.commit()
    response = await api_client.post(
        "/api/v3/auth/login",
        json={"username": f"{role}-user", "password": "goodpassword"},
    )
    assert response.status_code == 204


async def seed_profiles(api_engine: AsyncEngine) -> dict[str, int]:
    """Insert one row per profile type and return the IDs."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        quality = QualityProfile(
            name="quality-default",
            allowed_formats=["raw", "zip", "7z"],
            preferred_format="7z",
            require_dat_verified=False,
            upgrade_until_format="7z",
        )
        region = RegionProfile(
            name="region-default",
            priorities=["USA", "EUR"],
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
            template="{{ game.title }} ({{ release.region }})",
        )
        session.add_all([quality, region, dump, language, naming])
        await session.commit()
        await session.refresh(quality)
        await session.refresh(region)
        await session.refresh(dump)
        await session.refresh(language)
        await session.refresh(naming)
        return {
            "quality_profile_id": quality.id,
            "region_profile_id": region.id,
            "dump_profile_id": dump.id,
            "language_profile_id": language.id,
            "naming_profile_id": naming.id,
        }
