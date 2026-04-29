"""Tests for the ``romarr metadata reencrypt`` CLI stub (T067)."""

from __future__ import annotations

import pytest

from romarr.cli import main


def test_metadata_reencrypt_stub_raises_not_implemented() -> None:
    """The stub interface is parsable; running it raises the documented
    NotImplementedError so callers can layer against a stable surface
    while the rotation flow lands in a follow-up slice."""
    with pytest.raises(NotImplementedError, match=r"rotation implemented in 0\.2"):
        main(["metadata", "reencrypt", "--old-key", "old", "--new-key", "new"])


def test_metadata_reencrypt_requires_both_keys(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Argparse rejects invocations that drop either flag."""
    with pytest.raises(SystemExit):
        main(["metadata", "reencrypt", "--old-key", "old"])


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Bare ``romarr`` prints help and exits with the argparse usage code."""
    with pytest.raises(SystemExit):
        main([])
