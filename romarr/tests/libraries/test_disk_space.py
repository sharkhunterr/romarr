"""Pre-import disk-space gate tests (T031-T032)."""

from __future__ import annotations

from collections import namedtuple
from pathlib import Path

import pytest

from romarr.libraries.disk_space import check_min_disk_free
from romarr.libraries.errors import DiskFullError, LibraryUnavailable

_DiskUsage = namedtuple("_DiskUsage", ["total", "used", "free"])
_GIGABYTE = 1024 * 1024 * 1024


def test_above_threshold_passes(tmp_path: Path) -> None:
    """A real path on a developer/CI workstation has more than 1 GB
    free; the checker returns silently."""
    check_min_disk_free(tmp_path, min_gb=1)


def test_below_threshold_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``shutil.disk_usage`` returns < threshold ⇒ DiskFullError."""

    def fake_disk_usage(_path: object) -> _DiskUsage:
        return _DiskUsage(
            total=10 * _GIGABYTE, used=9 * _GIGABYTE, free=1 * _GIGABYTE
        )

    monkeypatch.setattr(
        "romarr.libraries.disk_space.shutil.disk_usage", fake_disk_usage
    )

    with pytest.raises(DiskFullError) as exc:
        check_min_disk_free(tmp_path, min_gb=5)
    # Free GB rendered into the message for the operator notification.
    assert "1.0 GB free" in str(exc.value)
    assert "5 GB" in str(exc.value)


def test_disk_full_is_library_unavailable_subclass() -> None:
    """The notification consumer treats every LibraryUnavailable the
    same way; DiskFullError must remain a subclass so the operator
    sees a distinct cause without changing the catch-clause shape."""
    assert issubclass(DiskFullError, LibraryUnavailable)
