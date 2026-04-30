"""Library model + Pydantic-validator tests (T006-T010)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.libraries.models import Library, LibraryPlatform
from romarr.libraries.schemas import LibraryCreate

# ---------------------------------------------------------------------------
# T006 — Library round-trip + CHECK constraints
# ---------------------------------------------------------------------------


async def test_library_round_trip(
    async_session: AsyncSession,
    tmp_library_path: Path,
    seeded_profile_ids: dict[str, int],
) -> None:
    library = Library(
        name="Cartridges",
        path=str(tmp_library_path),
        quality_profile_id=seeded_profile_ids["quality"],
        region_profile_id=seeded_profile_ids["region"],
        dump_profile_id=seeded_profile_ids["dump"],
        language_profile_id=seeded_profile_ids["language"],
        naming_profile_id=seeded_profile_ids["naming"],
    )
    async_session.add(library)
    await async_session.commit()

    row = (
        await async_session.execute(
            select(Library).where(Library.name == "Cartridges")
        )
    ).scalar_one()
    assert row.lifecycle_policy == "hardlink_and_seed"
    assert row.status == "ok"
    assert row.use_hardlinks is True


async def test_library_lifecycle_check_rejects_unknown(
    async_session: AsyncSession,
    tmp_library_path: Path,
    seeded_profile_ids: dict[str, int],
) -> None:
    library = Library(
        name="Cartridges",
        path=str(tmp_library_path),
        lifecycle_policy="seed_forever",
        quality_profile_id=seeded_profile_ids["quality"],
        region_profile_id=seeded_profile_ids["region"],
        dump_profile_id=seeded_profile_ids["dump"],
        language_profile_id=seeded_profile_ids["language"],
        naming_profile_id=seeded_profile_ids["naming"],
    )
    async_session.add(library)
    with pytest.raises(IntegrityError):
        await async_session.commit()


async def test_library_status_check_rejects_unknown(
    async_session: AsyncSession,
    tmp_library_path: Path,
    seeded_profile_ids: dict[str, int],
) -> None:
    library = Library(
        name="Cartridges",
        path=str(tmp_library_path),
        status="degraded",
        quality_profile_id=seeded_profile_ids["quality"],
        region_profile_id=seeded_profile_ids["region"],
        dump_profile_id=seeded_profile_ids["dump"],
        language_profile_id=seeded_profile_ids["language"],
        naming_profile_id=seeded_profile_ids["naming"],
    )
    async_session.add(library)
    with pytest.raises(IntegrityError):
        await async_session.commit()


# ---------------------------------------------------------------------------
# T007 — duplicate name rejected
# ---------------------------------------------------------------------------


async def test_library_unique_name(
    async_session: AsyncSession,
    tmp_library_path: Path,
    seeded_profile_ids: dict[str, int],
) -> None:
    common_kwargs: dict[str, object] = {
        "path": str(tmp_library_path),
        "quality_profile_id": seeded_profile_ids["quality"],
        "region_profile_id": seeded_profile_ids["region"],
        "dump_profile_id": seeded_profile_ids["dump"],
        "language_profile_id": seeded_profile_ids["language"],
        "naming_profile_id": seeded_profile_ids["naming"],
    }
    async_session.add(Library(name="Cartridges", **common_kwargs))
    await async_session.commit()

    async_session.add(Library(name="Cartridges", **common_kwargs))
    with pytest.raises(IntegrityError):
        await async_session.commit()


# ---------------------------------------------------------------------------
# T006b — m2m round-trip
# ---------------------------------------------------------------------------


async def test_library_platform_m2m_round_trip(
    async_session: AsyncSession,
    tmp_library_path: Path,
    seeded_profile_ids: dict[str, int],
) -> None:
    """A LibraryPlatform row requires a real platform.id; the Platform
    model lives in the foundation. This test creates a Platform inline
    so we don't drag in the platform-pack fixtures."""
    from romarr.domain.models import Platform

    platform = Platform(
        name="Sega Mega Drive",
        slug="megadrive",
    )
    library = Library(
        name="Cartridges",
        path=str(tmp_library_path),
        platforms_restricted=True,
        quality_profile_id=seeded_profile_ids["quality"],
        region_profile_id=seeded_profile_ids["region"],
        dump_profile_id=seeded_profile_ids["dump"],
        language_profile_id=seeded_profile_ids["language"],
        naming_profile_id=seeded_profile_ids["naming"],
    )
    async_session.add_all([platform, library])
    await async_session.commit()
    await async_session.refresh(platform)
    await async_session.refresh(library)

    async_session.add(
        LibraryPlatform(library_id=library.id, platform_id=platform.id)
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(LibraryPlatform).where(LibraryPlatform.library_id == library.id)
        )
    ).scalar_one()
    assert row.platform_id == platform.id


# ---------------------------------------------------------------------------
# T008 — Pydantic path validators
# ---------------------------------------------------------------------------


def test_library_create_rejects_relative_path(
    make_library_create_payload: Callable[..., dict[str, object]],
) -> None:
    payload = make_library_create_payload(path="relative/library")
    with pytest.raises(ValidationError) as exc:
        LibraryCreate.model_validate(payload)
    assert "absolute" in str(exc.value).lower()


def test_library_create_accepts_absolute_path(
    make_library_create_payload: Callable[..., dict[str, object]],
) -> None:
    payload = make_library_create_payload()
    LibraryCreate.model_validate(payload)


# ---------------------------------------------------------------------------
# T009 — restricted requires platforms
# ---------------------------------------------------------------------------


def test_library_create_restricted_requires_platforms(
    make_library_create_payload: Callable[..., dict[str, object]],
) -> None:
    payload = make_library_create_payload(
        platforms_restricted=True,
        platform_ids=[],
    )
    with pytest.raises(ValidationError) as exc:
        LibraryCreate.model_validate(payload)
    assert "platform" in str(exc.value).lower()


def test_library_create_restricted_with_platforms_ok(
    make_library_create_payload: Callable[..., dict[str, object]],
) -> None:
    payload = make_library_create_payload(
        platforms_restricted=True,
        platform_ids=[1, 2, 3],
    )
    LibraryCreate.model_validate(payload)


# ---------------------------------------------------------------------------
# T010 — RomM exporter requires URL + key
# ---------------------------------------------------------------------------


def test_library_create_romm_requires_url(
    make_library_create_payload: Callable[..., dict[str, object]],
) -> None:
    payload = make_library_create_payload(
        exporter_romm_enabled=True,
        exporter_romm_api_key="secret-key",
    )
    with pytest.raises(ValidationError) as exc:
        LibraryCreate.model_validate(payload)
    assert "url" in str(exc.value).lower()


def test_library_create_romm_requires_api_key(
    make_library_create_payload: Callable[..., dict[str, object]],
) -> None:
    payload = make_library_create_payload(
        exporter_romm_enabled=True,
        exporter_romm_url="https://romm.local",
    )
    with pytest.raises(ValidationError) as exc:
        LibraryCreate.model_validate(payload)
    assert "key" in str(exc.value).lower()


def test_library_create_romm_with_both_ok(
    make_library_create_payload: Callable[..., dict[str, object]],
) -> None:
    payload = make_library_create_payload(
        exporter_romm_enabled=True,
        exporter_romm_url="https://romm.local",
        exporter_romm_api_key="secret-key",
    )
    LibraryCreate.model_validate(payload)


# ---------------------------------------------------------------------------
# Bonus: min_disk_free_gb >= 1 (Pydantic field constraint)
# ---------------------------------------------------------------------------


def test_library_create_min_disk_must_be_positive(
    make_library_create_payload: Callable[..., dict[str, object]],
) -> None:
    payload = make_library_create_payload(min_disk_free_gb=0)
    with pytest.raises(ValidationError):
        LibraryCreate.model_validate(payload)
