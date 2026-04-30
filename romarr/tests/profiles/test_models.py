"""Profile model + Pydantic-validator tests (T006-T011)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.profiles.errors import RegexCompileError
from romarr.profiles.models import (
    CustomFormat,
    DumpProfile,
    LanguageProfile,
    LibraryCustomFormat,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)
from romarr.profiles.schemas import (
    CustomFormatCondition,
    QualityProfileCreate,
    RegionProfileCreate,
)

# ---------------------------------------------------------------------------
# T006 — round-trip + CHECK constraints
# ---------------------------------------------------------------------------


async def test_quality_profile_round_trip(async_session: AsyncSession) -> None:
    async_session.add(
        QualityProfile(
            name="Preservation",
            allowed_formats=["raw", "zip", "7z"],
            preferred_format="7z",
            require_dat_verified=True,
            upgrade_until_format="7z",
        )
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(QualityProfile).where(QualityProfile.name == "Preservation")
        )
    ).scalar_one()
    assert row.preferred_format == "7z"
    assert row.allowed_formats == ["raw", "zip", "7z"]
    assert row.is_factory_default is False
    assert row.is_user_modified is False


async def test_dump_profile_prefer_revision_check(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        DumpProfile(
            name="Bad",
            allowed_dump_status=["verified"],
            prefer_revision="bogus",
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_naming_profile_convention_check(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        NamingProfile(
            name="Bad",
            convention="not-a-real-one",
            template="{Game.Title}",
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_custom_format_score_range_check(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        CustomFormat(name="Out of range", score=10001, conditions=[])
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# T007 — UNIQUE name per type
# ---------------------------------------------------------------------------


async def test_unique_name_quality(async_session: AsyncSession) -> None:
    async_session.add(
        QualityProfile(
            name="Same",
            allowed_formats=["raw"],
            preferred_format="raw",
            upgrade_until_format="raw",
        )
    )
    await async_session.commit()

    async_session.add(
        QualityProfile(
            name="Same",
            allowed_formats=["zip"],
            preferred_format="zip",
            upgrade_until_format="zip",
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_unique_name_naming(async_session: AsyncSession) -> None:
    async_session.add(
        NamingProfile(name="Same", convention="no-intro", template="{Game.Title}")
    )
    await async_session.commit()
    async_session.add(
        NamingProfile(name="Same", convention="redump", template="{Game.Title}")
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# T008 — m2m composite PK
# ---------------------------------------------------------------------------


async def test_m2m_composite_pk_rejects_duplicate(
    async_session: AsyncSession,
) -> None:
    fmt = CustomFormat(name="X", score=10, conditions=[])
    async_session.add(fmt)
    await async_session.commit()
    await async_session.refresh(fmt)

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    async_session.add(
        LibraryCustomFormat(library_id=1, custom_format_id=fmt.id, created_at=now)
    )
    await async_session.commit()

    async_session.add(
        LibraryCustomFormat(library_id=1, custom_format_id=fmt.id, created_at=now)
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# T009 — Quality validators
# ---------------------------------------------------------------------------


def test_quality_preferred_must_be_in_allowed() -> None:
    with pytest.raises(ValidationError, match="preferred_format must be one of"):
        QualityProfileCreate(
            name="Bad",
            allowed_formats=["raw", "zip"],
            preferred_format="7z",  # not in allowed
            upgrade_until_format="raw",
        )


def test_quality_upgrade_until_must_be_in_allowed() -> None:
    with pytest.raises(ValidationError, match="upgrade_until_format must be one of"):
        QualityProfileCreate(
            name="Bad",
            allowed_formats=["raw"],
            preferred_format="raw",
            upgrade_until_format="7z",  # not in allowed
        )


def test_quality_allowed_formats_min_length() -> None:
    with pytest.raises(ValidationError):
        QualityProfileCreate(
            name="Bad",
            allowed_formats=[],  # empty rejected
            preferred_format="raw",
            upgrade_until_format="raw",
        )


# ---------------------------------------------------------------------------
# T010 — Region invariants
# ---------------------------------------------------------------------------


def test_region_empty_priorities_no_fallback_rejected() -> None:
    with pytest.raises(ValidationError, match="reject every release"):
        RegionProfileCreate(
            name="Bad",
            priorities=[],
            allow_fallback_outside_priorities=False,
        )


def test_region_overlap_priorities_exclude_rejected() -> None:
    with pytest.raises(ValidationError, match="appear in both"):
        RegionProfileCreate(
            name="Bad",
            priorities=["USA", "EUR"],
            exclude_regions=["USA"],
        )


def test_region_empty_priorities_with_fallback_ok() -> None:
    profile = RegionProfileCreate(
        name="Permissive",
        priorities=[],
        allow_fallback_outside_priorities=True,
    )
    assert profile.priorities == []


# ---------------------------------------------------------------------------
# T011 — Custom Format regex compile validator
# ---------------------------------------------------------------------------


def test_invalid_regex_rejected() -> None:
    with pytest.raises(RegexCompileError, match="invalid regex"):
        CustomFormatCondition(
            field="tags", operator="matches_regex", values="[invalid("
        )


def test_valid_regex_accepted() -> None:
    cond = CustomFormatCondition(
        field="tags", operator="matches_regex", values=r"\[!\]"
    )
    assert cond.values == r"\[!\]"


def test_greater_than_requires_release_size() -> None:
    with pytest.raises(ValidationError, match="release_size"):
        CustomFormatCondition(field="tags", operator="greater_than", values=100)


def test_in_requires_list() -> None:
    with pytest.raises(ValidationError, match="requires a list"):
        CustomFormatCondition(field="region", operator="in", values="USA")


# ---------------------------------------------------------------------------
# Each profile type round-trips
# ---------------------------------------------------------------------------


async def test_region_profile_round_trip(async_session: AsyncSession) -> None:
    async_session.add(
        RegionProfile(
            name="USA First",
            priorities=["USA", "EUR", "World", "JPN"],
            allow_fallback_outside_priorities=True,
            exclude_regions=[],
        )
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(RegionProfile).where(RegionProfile.name == "USA First")
        )
    ).scalar_one()
    assert row.priorities == ["USA", "EUR", "World", "JPN"]


async def test_language_profile_round_trip(async_session: AsyncSession) -> None:
    async_session.add(
        LanguageProfile(
            name="EN Only",
            required_languages=["en"],
            preferred_languages=["en", "multi"],
            exclude_japanese_only=True,
        )
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(LanguageProfile).where(LanguageProfile.name == "EN Only")
        )
    ).scalar_one()
    assert row.required_languages == ["en"]
