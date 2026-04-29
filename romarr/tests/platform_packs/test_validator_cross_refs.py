"""Cross-reference checks: dangling parents, cycles, duplicates,
adversarial regex (T014, T015, T016, T017)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.platform_packs.errors import PackValidationError
from romarr.platform_packs.validator import validate_pack


def test_dangling_parent_rejected(
    pack_yaml: Callable[[str], bytes],
) -> None:
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(pack_yaml("invalid_refs/dangling_parent.yaml"))
    codes = {v.code for v in exc_info.value.violations}
    assert "dangling_parent" in codes
    # The violation messages name the bad slug for the API layer.
    messages = " ".join(v.message for v in exc_info.value.violations)
    assert "nes-that-doesnt-exist" in messages


def test_dangling_parent_satisfied_by_existing_db_slug(
    pack_yaml: Callable[[str], bytes],
) -> None:
    """When the parent slug already lives in the DB, the pack passes."""
    parsed = validate_pack(
        pack_yaml("invalid_refs/dangling_parent.yaml"),
        existing_slugs={"nes-that-doesnt-exist"},
    )
    assert parsed.parsed["platforms"][0]["parent_platform_slug"] == "nes-that-doesnt-exist"


def test_cycle_a_b_rejected(
    pack_yaml: Callable[[str], bytes],
) -> None:
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(pack_yaml("invalid_refs/parent_cycle_a_b.yaml"))
    codes = {v.code for v in exc_info.value.violations}
    assert "parent_cycle" in codes
    msg = str(exc_info.value)
    assert "a" in msg and "b" in msg


def test_cycle_a_b_c_rejected_naming_all_members(
    pack_yaml: Callable[[str], bytes],
) -> None:
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(pack_yaml("invalid_refs/parent_cycle_a_b_c.yaml"))
    msg = str(exc_info.value)
    for slug in ("a", "b", "c"):
        assert slug in msg


def test_duplicate_slug_rejected(
    pack_yaml: Callable[[str], bytes],
) -> None:
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(pack_yaml("invalid_schema/duplicate_slug.yaml"))
    codes = {v.code for v in exc_info.value.violations}
    assert "duplicate_slug" in codes


def test_duplicate_extension_rejected(
    pack_yaml: Callable[[str], bytes],
) -> None:
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(pack_yaml("invalid_schema/duplicate_extension.yaml"))
    codes = {v.code for v in exc_info.value.violations}
    assert "duplicate_extension" in codes


def test_too_many_platforms_rejected() -> None:
    """The pack-level platform cap (FR-001c, MAX_PLATFORMS_PER_PACK=200)
    is enforced cross-ref-wise after schema validation."""
    body = "pack_version: '2026.04.099'\nschema_version: 1\nplatforms:\n"
    for i in range(201):
        body += (
            f"  - slug: p{i}\n    name: P{i}\n    manufacturer: ACME\n"
            "    formats:\n      - extension: '.x'\n        format_type: cartridge\n"
        )
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(body.encode())
    codes = {v.code for v in exc_info.value.violations}
    assert "too_many_platforms" in codes


def test_pathological_regex_rejected_on_time_bound() -> None:
    """A catastrophically-backtracking regex blows the 50 ms budget."""
    body = (
        "pack_version: '2026.04.099'\nschema_version: 1\n"
        "parsing_strategies:\n"
        "  - id: bad-strategy\n"
        # Classic ReDoS: `(a+)+$` on a long all-a input degrades exponentially.
        "    regex: '(a+)+$'\n"
        "platforms:\n"
        "  - slug: nes\n    name: NES\n    manufacturer: Nintendo\n"
        "    formats:\n      - extension: '.nes'\n        format_type: cartridge\n"
    )
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(body.encode())
    codes = {v.code for v in exc_info.value.violations}
    assert "regex_timeout" in codes


def test_invalid_regex_syntax_rejected() -> None:
    body = (
        "pack_version: '2026.04.099'\nschema_version: 1\n"
        "parsing_strategies:\n"
        "  - id: bad-strategy\n"
        "    regex: '(unclosed'\n"
        "platforms:\n"
        "  - slug: nes\n    name: NES\n    manufacturer: Nintendo\n"
        "    formats:\n      - extension: '.nes'\n        format_type: cartridge\n"
    )
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(body.encode())
    codes = {v.code for v in exc_info.value.violations}
    assert "regex_invalid" in codes
