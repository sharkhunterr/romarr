"""Module-local fixtures for metadata tests.

Sets a deterministic ``ROMARR_AUTH_SECRET_KEY`` so the encryption
helper can derive a stable Fernet key for every test run, and points
``ROMARR_DATA_DIR`` at a per-test tmp dir so cover writes don't
collide with each other or with the developer's local data tree.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from romarr.config.settings import get_settings


@pytest.fixture
def metadata_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Point settings at a temp data dir + a fixed secret key for the test."""
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret-key-do-not-use-in-prod")
    monkeypatch.setenv("ROMARR_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
