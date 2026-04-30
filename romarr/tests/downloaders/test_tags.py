"""Tag helper tests."""

from __future__ import annotations

import pytest

from romarr.downloaders.tags import (
    TAG_IMPORTED,
    TAG_ROMARR,
    standard_tag_set,
    tag_for_platform,
)


def test_constants() -> None:
    assert TAG_ROMARR == "romarr"
    assert TAG_IMPORTED == "romarr-imported"


def test_tag_for_platform() -> None:
    assert tag_for_platform("megadrive") == "romarr-megadrive"
    assert tag_for_platform("snes") == "romarr-snes"


def test_tag_for_platform_rejects_empty() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        tag_for_platform("")


def test_standard_tag_set_preserves_order() -> None:
    assert standard_tag_set("megadrive") == ["romarr", "romarr-megadrive"]
