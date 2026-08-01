"""Tests for the platform_pack community adapter — specifically
the manifest-driven pack_version injection so operators can omit
``pack_version`` from their YAML and let the manifest carry the
single-source-of-truth version.
"""

from __future__ import annotations

import yaml

from romarr.community.platform_pack_adapter import _ensure_pack_version


def test_injects_pack_version_when_absent() -> None:
    body = b"""schema_version: 1
description: My community pack
platforms:
  - slug: nes
    name: NES
"""
    out = _ensure_pack_version(body, "2026.07.30")
    parsed = yaml.safe_load(out)
    assert parsed["pack_version"] == "2026.07.30"
    # Existing fields preserved.
    assert parsed["schema_version"] == 1
    assert parsed["description"] == "My community pack"
    assert parsed["platforms"][0]["slug"] == "nes"


def test_keeps_yaml_pack_version_when_present() -> None:
    body = b"""pack_version: "9.9.9"
schema_version: 1
platforms: []
"""
    out = _ensure_pack_version(body, "0.0.1-fallback")
    parsed = yaml.safe_load(out)
    # The YAML's own pack_version wins — the adapter never overrides
    # a value the operator wrote explicitly.
    assert parsed["pack_version"] == "9.9.9"


def test_malformed_yaml_falls_through_untouched() -> None:
    body = b":: not: valid ["
    out = _ensure_pack_version(body, "2026.07.30")
    # Ingestor's own validator will surface the parse error; adapter
    # must not swallow it.
    assert out == body


def test_non_mapping_root_falls_through_untouched() -> None:
    # A YAML list at the root — not a valid pack, but we don't want
    # to mask it by silently injecting a version.
    body = b"- one\n- two\n"
    out = _ensure_pack_version(body, "2026.07.30")
    assert out == body
