"""Module-local fixtures for the downloaders test suite."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def sab_fixture() -> Callable[[str], bytes]:
    """Loader for SABnzbd JSON fixtures under ``tests/fixtures/sabnzbd/``."""

    def _load(name: str) -> bytes:
        path = _FIXTURES / "sabnzbd" / name
        if not path.is_file():
            raise FileNotFoundError(f"SAB fixture not found: {path}")
        return path.read_bytes()

    return _load
