"""JSON Schema validator tests (T013, T018).

Iterates the broken-pack fixtures under
``tests/fixtures/packs/invalid_schema/``; every file MUST be rejected
with a :class:`PackValidationError` whose ``violations`` cite the
right JSON path. SC-004 requires ≥ 20 broken-pack fixtures.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from romarr.platform_packs.errors import (
    PackValidationError,
    SchemaVersionTooHighError,
)
from romarr.platform_packs.validator import validate_pack

_INVALID_SCHEMA_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "packs"
    / "invalid_schema"
)


def _list_invalid_schema_fixtures() -> list[Path]:
    return sorted(p for p in _INVALID_SCHEMA_DIR.iterdir() if p.suffix == ".yaml")


def test_at_least_twenty_invalid_schema_fixtures_exist() -> None:
    """SC-004: the broken-pack corpus has ≥ 20 entries."""
    fixtures = _list_invalid_schema_fixtures()
    assert len(fixtures) >= 20, (
        f"expected ≥ 20 broken-pack fixtures, found {len(fixtures)}"
    )


@pytest.mark.parametrize(
    "fixture_path",
    _list_invalid_schema_fixtures(),
    ids=lambda p: p.name,
)
def test_invalid_schema_fixture_is_rejected(
    fixture_path: Path,
) -> None:
    body = fixture_path.read_bytes()
    with pytest.raises(PackValidationError):
        validate_pack(body)


def test_schema_version_too_high_raises_specific_error(
    pack_yaml: Callable[[str], bytes],
) -> None:
    body = pack_yaml("invalid_schema/schema_version_too_high.yaml")
    with pytest.raises(SchemaVersionTooHighError) as exc_info:
        validate_pack(body)
    assert exc_info.value.requested == 99
    assert exc_info.value.supported == 1


def test_violation_path_pinpoints_offending_field(
    pack_yaml: Callable[[str], bytes],
) -> None:
    body = pack_yaml("invalid_schema/missing_pack_version.yaml")
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(body)
    paths = {v.path for v in exc_info.value.violations}
    # Either the root /(missing required) or specifically /pack_version.
    assert "/" in paths or "/pack_version" in paths


def test_truncated_yaml_raises_with_yaml_parse_error_code(
    pack_yaml: Callable[[str], bytes],
) -> None:
    body = pack_yaml("invalid_yaml/truncated.yaml")
    with pytest.raises(PackValidationError) as exc_info:
        validate_pack(body)
    codes = {v.code for v in exc_info.value.violations}
    assert "yaml_parse_error" in codes


def test_valid_minimal_pack_passes(
    pack_yaml: Callable[[str], bytes],
) -> None:
    parsed = validate_pack(pack_yaml("valid/minimal.yaml"))
    assert parsed.pack_version == "2026.04.001"
    assert len(parsed.contents_hash) == 64
    assert parsed.parsed["platforms"][0]["slug"] == "megadrive"


def test_valid_two_platforms_pack_passes(
    pack_yaml: Callable[[str], bytes],
) -> None:
    parsed = validate_pack(pack_yaml("valid/two_platforms.yaml"))
    assert parsed.pack_version == "2026.04.002"
    assert {p["slug"] for p in parsed.parsed["platforms"]} == {"nes", "snes"}
