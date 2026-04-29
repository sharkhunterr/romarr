"""YAML loader + canonicalization tests (T012)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import yaml

from romarr.platform_packs.yaml_loader import (
    MAX_PACK_BYTES,
    PackTooLargeError,
    canonicalize,
    compute_contents_hash,
    load_pack,
)


def test_load_pack_parses_minimal_pack(pack_yaml: Callable[[str], bytes]) -> None:
    parsed = load_pack(pack_yaml("valid/minimal.yaml"))
    assert parsed["pack_version"] == "2026.04.001"
    assert parsed["platforms"][0]["slug"] == "megadrive"


def test_load_pack_rejects_oversize_payload() -> None:
    body = b"a" * (MAX_PACK_BYTES + 1)
    with pytest.raises(PackTooLargeError):
        load_pack(body)


def test_load_pack_rejects_top_level_list() -> None:
    with pytest.raises(yaml.YAMLError):
        load_pack(b"- item-1\n- item-2\n")


def test_load_pack_handles_empty_input() -> None:
    assert load_pack(b"") == {}


def test_canonicalize_is_stable_across_key_order() -> None:
    a = {"pack_version": "2026.04.099", "schema_version": 1, "platforms": []}
    b = {"platforms": [], "schema_version": 1, "pack_version": "2026.04.099"}
    assert canonicalize(a) == canonicalize(b)


def test_canonicalize_is_stable_across_yaml_whitespace_edits(
    pack_yaml: Callable[[str], bytes],
) -> None:
    """The hash MUST be stable when only YAML cosmetic edits change."""
    parsed = load_pack(pack_yaml("valid/minimal.yaml"))
    h1 = compute_contents_hash(parsed)

    # Simulate "operator added trailing whitespace + a comment" by
    # building a re-emitted YAML that round-trips through PyYAML.
    re_emitted = yaml.safe_dump(parsed, sort_keys=False, default_flow_style=False)
    parsed_again = load_pack(re_emitted.encode("utf-8"))
    h2 = compute_contents_hash(parsed_again)

    assert h1 == h2


def test_canonicalize_changes_when_data_changes(
    pack_yaml: Callable[[str], bytes],
) -> None:
    parsed = load_pack(pack_yaml("valid/minimal.yaml"))
    h1 = compute_contents_hash(parsed)
    parsed["description"] = "different"
    h2 = compute_contents_hash(parsed)
    assert h1 != h2
