"""Module-local fixtures for profile tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.profiles.types import ReleaseFacts


def _facts(**overrides: object) -> ReleaseFacts:
    base: dict[str, object] = {
        "title": "Sonic the Hedgehog",
        "regions": ("USA",),
        "languages": ("en",),
        "revision": None,
        "dump_status": DumpStatus.VERIFIED,
        "tags": (),
        "naming_convention": NamingConvention.NO_INTRO,
        "file_format": "raw",
        "dat_verified": True,
        "indexer_source": "torznab",
        "release_size": 1_000_000,
        "release_group": None,
    }
    base.update(overrides)
    return ReleaseFacts(**base)  # type: ignore[arg-type]


@pytest.fixture
def make_facts() -> Callable[..., ReleaseFacts]:
    """Build a :class:`ReleaseFacts` with sensible defaults; pass kwargs to override."""
    return _facts
