"""Pre-import disk-space gate (spec 009 — Phase 5 DISK).

Per FR-030 every import targeting a library must verify the path
has at least ``library.min_disk_free_gb`` free before the move /
hardlink runs. The check is a pure wrapper around
:func:`shutil.disk_usage` that converts bytes-free into gigabytes
(binary, ``2**30``) and raises :class:`DiskFullError` when the
threshold isn't met.

Tests monkeypatch ``shutil.disk_usage`` for the below-threshold
case; the above-threshold case relies on a real path the test
fixture sets up.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from romarr.libraries.errors import DiskFullError

if TYPE_CHECKING:
    from pathlib import Path

_GIGABYTE = 1024 * 1024 * 1024


def check_min_disk_free(path: Path, min_gb: int) -> None:
    """Raise :class:`DiskFullError` iff ``path`` has fewer than
    ``min_gb`` gigabytes free.

    Pure (modulo the ``shutil.disk_usage`` system call). The error
    message is operator-facing and reports the actual free GB so
    notifications can render a helpful warning.
    """
    usage = shutil.disk_usage(path)
    free_gb = usage.free / _GIGABYTE
    if free_gb < min_gb:
        raise DiskFullError(
            f"library at {path}: {free_gb:.1f} GB free, "
            f"requires {min_gb} GB minimum",
        )


__all__ = ["check_min_disk_free"]
