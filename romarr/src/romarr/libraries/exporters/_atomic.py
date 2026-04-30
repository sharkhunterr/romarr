"""Shared atomic-write + advisory-lock helper for per-platform
filesystem exporters (ES-DE, Pegasus, LaunchBox).

FR-017 (atomic): write to ``<filename>.tmp`` then :func:`os.replace`;
a crash mid-write preserves the prior file.

FR-017a (lock): per-output advisory lock at
``<target_dir>/.<filename>.lock`` acquired with
:func:`fcntl.flock(LOCK_EX | LOCK_NB)`. When unavailable, the
writer **coalesces** — returns ``False`` without re-emitting.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@contextlib.contextmanager
def _exporter_lock(target_dir: Path, lock_name: str) -> Iterator[bool]:
    """Acquire the advisory lock at
    ``<target_dir>/.<lock_name>.lock``.

    Yields ``True`` when the lock was acquired, ``False`` when
    contended. The lock is released on context exit and on process
    death (``fcntl.flock`` natively).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    lock_path = target_dir / f".{lock_name}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def write_atomic_with_lock(
    *,
    target_dir: Path,
    filename: str,
    body: bytes,
) -> bool:
    """Write ``body`` to ``<target_dir>/<filename>`` atomically.

    Returns ``True`` on success, ``False`` when another process
    holds the per-output advisory lock (the writer coalesces).
    Uses ``<filename>`` as the lock name so each exporter output
    gets its own lock file (e.g., ``.gamelist.lock``,
    ``.metadata.lock``, ``.launchbox-export.lock``).
    """
    with _exporter_lock(target_dir, filename) as acquired:
        if not acquired:
            return False

        target = target_dir / filename
        tmp = target_dir / f"{filename}.tmp"
        try:
            tmp.write_bytes(body)
            os.replace(tmp, target)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                tmp.unlink()
            raise
        return True


__all__ = ["write_atomic_with_lock"]
