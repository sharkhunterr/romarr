"""Domain-layer validators.

These are pure functions used by Pydantic schemas (Read/Create/Update)
and by the seeder. They encode the constraints expressed informally
in spec 001 — slug shape (FR-007), hash hex shape (FR-014), ISO
region/language codes (Assumptions), multi-disc invariant (FR-004).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Constants -----------------------------------------------------------------

#: kebab-case slug per FR-007 (lowercase, digits, single hyphens).
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: ISO-3166-1 alpha-2 region code (always two uppercase letters).
REGION_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")

#: ISO-639-1 language code (always two lowercase letters).
LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2}$")

#: Hex-string hash patterns sized to each algorithm's bit width.
CRC32_PATTERN = re.compile(r"^[0-9a-f]{8}$")
MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


# Slug -----------------------------------------------------------------------


def validate_slug(value: str) -> str:
    """Return ``value`` unchanged if it is a valid kebab-case slug.

    Raises :class:`ValueError` otherwise. Callers (Pydantic field
    validators) expect a string-in / string-out contract.
    """
    if not SLUG_PATTERN.match(value):
        raise ValueError(
            f"slug must be lowercase kebab-case (a-z, 0-9, single hyphens); got {value!r}"
        )
    return value


# Region / language codes ---------------------------------------------------


def validate_region_code(value: str) -> str:
    """Validate a single ISO-3166-1 alpha-2 region code (e.g., ``US``)."""
    if not REGION_CODE_PATTERN.match(value):
        raise ValueError(f"region code must be ISO-3166-1 alpha-2 (two uppercase); got {value!r}")
    return value


def validate_region_list(value: Iterable[str]) -> list[str]:
    """Validate a list of region codes, returning a sorted dedup'd copy.

    Sorted output is canonical so the same logical region set always
    serializes to the same JSON array.
    """
    return sorted({validate_region_code(v) for v in value})


def validate_language_code(value: str) -> str:
    """Validate a single ISO-639-1 language code (e.g., ``en``)."""
    if not LANGUAGE_CODE_PATTERN.match(value):
        raise ValueError(
            f"language code must be ISO-639-1 (two lowercase); got {value!r}"
        )
    return value


def validate_language_list(value: Iterable[str]) -> list[str]:
    """Validate a list of language codes, returning a sorted dedup'd copy."""
    return sorted({validate_language_code(v) for v in value})


# Hashes --------------------------------------------------------------------


def validate_crc32(value: str) -> str:
    if not CRC32_PATTERN.match(value):
        raise ValueError(f"crc32 must be 8 lowercase hex chars; got {value!r}")
    return value


def validate_md5(value: str) -> str:
    if not MD5_PATTERN.match(value):
        raise ValueError(f"md5 must be 32 lowercase hex chars; got {value!r}")
    return value


def validate_sha1(value: str) -> str:
    if not SHA1_PATTERN.match(value):
        raise ValueError(f"sha1 must be 40 lowercase hex chars; got {value!r}")
    return value


def validate_sha256(value: str) -> str:
    if not SHA256_PATTERN.match(value):
        raise ValueError(f"sha256 must be 64 lowercase hex chars; got {value!r}")
    return value


# Cross-field invariants ----------------------------------------------------


def validate_multi_disc(
    *, disc_number: int, disc_total: int, parent_release_id: int | None
) -> None:
    """Enforce FR-004 at the schema layer (a backstop to the DB CHECK).

    Rules:
      - ``disc_number`` and ``disc_total`` are positive (≥ 1).
      - ``disc_number > 1`` requires ``parent_release_id`` to be set.
      - ``disc_total >= disc_number`` (a 2-of-3 disc set is impossible).
    """
    if disc_number < 1:
        raise ValueError("disc_number must be >= 1")
    if disc_total < 1:
        raise ValueError("disc_total must be >= 1")
    if disc_total < disc_number:
        raise ValueError("disc_total must be >= disc_number")
    if disc_number > 1 and parent_release_id is None:
        raise ValueError(
            "disc_number > 1 requires parent_release_id (FR-004)"
        )


# DAT entry hash invariant --------------------------------------------------


def require_at_least_one_hash(
    *, crc32: str | None, md5: str | None, sha1: str | None
) -> None:
    """Enforce FR-006 at the schema layer."""
    if not (crc32 or md5 or sha1):
        raise ValueError("dat_entry must carry at least one of crc32, md5, sha1")
