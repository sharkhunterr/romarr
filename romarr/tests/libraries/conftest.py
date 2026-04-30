"""Module-local fixtures for libraries tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.profiles.models import (
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)


@pytest.fixture
def tmp_library_path(tmp_path: Path) -> Path:
    """Return a writable directory the tests can pass as ``library.path``."""
    root = tmp_path / "library"
    root.mkdir()
    return root


@pytest_asyncio.fixture
async def seeded_profile_ids(
    async_session: AsyncSession,
) -> dict[str, int]:
    """Insert one row of each of the five profile types and return
    their primary keys so library tests can satisfy the NOT NULL FK
    columns without orchestrating spec 006's seeders."""
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
    async_session.add_all([quality, region, dump, language, naming])
    await async_session.commit()
    await async_session.refresh(quality)
    await async_session.refresh(region)
    await async_session.refresh(dump)
    await async_session.refresh(language)
    await async_session.refresh(naming)
    return {
        "quality": quality.id,
        "region": region.id,
        "dump": dump.id,
        "language": language.id,
        "naming": naming.id,
    }


@pytest.fixture
def make_library_create_payload(
    tmp_library_path: Path,
    seeded_profile_ids: dict[str, int],
) -> Callable[..., dict[str, object]]:
    """Helper that builds a kwargs dict for :class:`LibraryCreate`
    with overridable fields, satisfying every NOT NULL FK from
    ``seeded_profile_ids``."""

    def _build(**overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "name": "Cartridges",
            "path": str(tmp_library_path),
            "quality_profile_id": seeded_profile_ids["quality"],
            "region_profile_id": seeded_profile_ids["region"],
            "dump_profile_id": seeded_profile_ids["dump"],
            "language_profile_id": seeded_profile_ids["language"],
            "naming_profile_id": seeded_profile_ids["naming"],
        }
        base.update(overrides)
        return base

    return _build
