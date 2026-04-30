"""Module-local fixtures for indexer tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

_FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def torznab_response() -> Callable[[str], bytes]:
    """Loader for fixture XML by relative path under tests/fixtures/."""

    def _load(name: str) -> bytes:
        path = _FIXTURES_ROOT / name
        if not path.is_file():
            raise FileNotFoundError(
                f"torznab fixture {name!r} not found at {path}"
            )
        return path.read_bytes()

    return _load
