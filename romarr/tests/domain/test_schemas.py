"""Pydantic schema tests — `*Read`/`*Create`/`*Update` shapes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.schemas import (
    DatEntryCreate,
    DumpCreate,
    GameCreate,
    PlatformCreate,
    PlatformUpdate,
    ReleaseCreate,
)


def test_platform_create_minimal() -> None:
    p = PlatformCreate(slug="nes", name="Nintendo Entertainment System")
    assert p.slug == "nes"
    assert p.newznab_category_ids == []  # default factory


def test_platform_create_rejects_invalid_slug() -> None:
    with pytest.raises(ValidationError):
        PlatformCreate(slug="NES", name="bad")


def test_platform_create_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        PlatformCreate(slug="nes", name="x", unknown_field="oops")  # type: ignore[call-arg]


def test_platform_update_all_fields_optional() -> None:
    p = PlatformUpdate()  # nothing supplied → still valid
    assert p.name is None


def test_game_create_normalizes() -> None:
    g = GameCreate(platform_id=1, slug="sonic", title="Sonic")
    assert g.title == "Sonic"


def test_release_create_normalizes_regions_languages() -> None:
    r = ReleaseCreate(
        game_id=1,
        name="Sonic (USA, EUR)",
        regions=["EU", "US", "US"],  # dup + unsorted
        languages=["fr", "en", "fr"],
    )
    assert r.regions == ["EU", "US"]
    assert r.languages == ["en", "fr"]


def test_release_create_disc2_without_parent_rejected() -> None:
    with pytest.raises(ValidationError, match="parent_release_id"):
        ReleaseCreate(
            game_id=1,
            name="Disc 2",
            disc_number=2,
            disc_total=2,
            parent_release_id=None,
        )


def test_dump_create_validates_hashes() -> None:
    d = DumpCreate(
        release_id=1,
        path="/library/sonic.md",
        original_filename="sonic.md",
        size_bytes=524288,
        format=".md",
        crc32="deadbeef",
        md5="0" * 32,
        sha1="a" * 40,
    )
    assert d.crc32 == "deadbeef"


def test_dump_create_rejects_uppercase_hash() -> None:
    with pytest.raises(ValidationError):
        DumpCreate(
            release_id=1,
            path="/lib/x",
            original_filename="x",
            size_bytes=1,
            format=".md",
            crc32="DEADBEEF",
            md5="0" * 32,
            sha1="0" * 40,
        )


def test_dat_entry_create_requires_at_least_one_hash() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        DatEntryCreate(
            platform_id=1,
            source="no-intro",
            name="Sonic",
            crc32=None,
            md5=None,
            sha1=None,
            status=DumpStatus.VERIFIED,
            dat_contents_hash="0" * 64,
        )


def test_dat_entry_create_with_just_sha1_passes() -> None:
    e = DatEntryCreate(
        platform_id=1,
        source="no-intro",
        name="Sonic",
        sha1="a" * 40,
        dat_contents_hash="0" * 64,
    )
    assert e.sha1 == "a" * 40


def test_release_create_default_dump_status_unknown() -> None:
    r = ReleaseCreate(game_id=1, name="Sonic (USA)")
    assert r.dump_status == DumpStatus.UNKNOWN
    assert r.naming_convention == NamingConvention.UNKNOWN
