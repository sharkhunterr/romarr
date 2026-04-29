"""Module-local fixtures for platform-pack tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

_FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "packs"


@pytest.fixture
def pack_yaml() -> Callable[[str], bytes]:
    """Returns a loader that reads a fixture YAML by relative path."""

    def _load(name: str) -> bytes:
        path = _FIXTURES_ROOT / name
        if not path.is_file():
            raise FileNotFoundError(f"pack fixture {name!r} not found at {path}")
        return path.read_bytes()

    return _load
