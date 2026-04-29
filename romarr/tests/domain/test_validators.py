"""Domain validator unit tests — pure functions, no DB."""

from __future__ import annotations

import pytest

from romarr.domain.validators import (
    require_at_least_one_hash,
    validate_crc32,
    validate_language_list,
    validate_md5,
    validate_multi_disc,
    validate_region_code,
    validate_region_list,
    validate_sha1,
    validate_sha256,
    validate_slug,
)


@pytest.mark.parametrize("slug", ["nes", "snes", "megadrive", "game-boy", "psx-mod-2"])
def test_slug_valid(slug: str) -> None:
    assert validate_slug(slug) == slug


@pytest.mark.parametrize(
    "slug",
    [
        "",
        "NES",        # uppercase
        "no_intro",   # underscore
        "no--intro",  # double hyphen
        "-leading",
        "trailing-",
        "with space",
    ],
)
def test_slug_rejects_invalid_shapes(slug: str) -> None:
    with pytest.raises(ValueError, match="kebab-case"):
        validate_slug(slug)


def test_region_codes_normalize_sort_dedup() -> None:
    assert validate_region_list(["EU", "US", "US", "JP"]) == ["EU", "JP", "US"]


def test_region_code_rejects_lowercase() -> None:
    with pytest.raises(ValueError):
        validate_region_code("us")


def test_language_codes_normalize_sort_dedup() -> None:
    assert validate_language_list(["fr", "en", "fr", "ja"]) == ["en", "fr", "ja"]


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (validate_crc32, "deadbeef"),
        (validate_md5, "0" * 32),
        (validate_sha1, "a" * 40),
        (validate_sha256, "f" * 64),
    ],
)
def test_hash_validators_accept_correct_lengths(
    validator: object, value: str
) -> None:
    assert validator(value) == value  # type: ignore[operator]


@pytest.mark.parametrize(
    ("validator", "bad"),
    [
        (validate_crc32, "DEADBEEF"),    # uppercase
        (validate_crc32, "deadbeef0"),   # too long
        (validate_md5, "0" * 31),
        (validate_sha1, "g" * 40),       # not hex
        (validate_sha256, "0" * 63),
    ],
)
def test_hash_validators_reject_bad_shapes(validator: object, bad: str) -> None:
    with pytest.raises(ValueError):
        validator(bad)  # type: ignore[operator]


def test_multi_disc_invariant_disc1_no_parent_ok() -> None:
    validate_multi_disc(disc_number=1, disc_total=1, parent_release_id=None)
    validate_multi_disc(disc_number=1, disc_total=2, parent_release_id=None)


def test_multi_disc_disc2_requires_parent() -> None:
    with pytest.raises(ValueError, match="parent_release_id"):
        validate_multi_disc(disc_number=2, disc_total=2, parent_release_id=None)


def test_multi_disc_total_must_be_at_least_disc_number() -> None:
    with pytest.raises(ValueError, match=">= disc_number"):
        validate_multi_disc(disc_number=3, disc_total=2, parent_release_id=1)


def test_multi_disc_zero_invalid() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        validate_multi_disc(disc_number=0, disc_total=1, parent_release_id=None)


def test_require_at_least_one_hash_pass() -> None:
    require_at_least_one_hash(crc32="deadbeef", md5=None, sha1=None)
    require_at_least_one_hash(crc32=None, md5="0" * 32, sha1=None)
    require_at_least_one_hash(crc32=None, md5=None, sha1="a" * 40)


def test_require_at_least_one_hash_all_none_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        require_at_least_one_hash(crc32=None, md5=None, sha1=None)
