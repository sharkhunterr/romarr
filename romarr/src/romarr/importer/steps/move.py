"""Atomic move/hardlink step (FR-024, FR-025, FR-026 / pipeline step 10).

The riskiest piece of the importer. The contract:

  1. **Idempotent re-import** (FR-025): if ``dest`` already exists
     and its SHA-1 matches ``expected_sha1``, return a coalesced
     no-op success.
  2. **Destination collision** (FR-026): if ``dest`` exists with a
     different SHA-1 and ``force=False``, raise
     ``MoveError(rejection_reason='destination_collision')`` and
     leave both files untouched. ``force=True`` overwrites.
  3. **Hardlink-first** (FR-024 / SC-003): try ``os.link(source,
     dest)``. On the same filesystem this is constant-space and
     instant.
  4. **Cross-fs fallback**: ``OSError(EXDEV)`` from the hardlink
     ⇒ copy ``source`` to ``dest.tmp``, verify SHA-1 matches, then
     ``os.replace(dest.tmp, dest)``. A mid-copy crash (or
     ``OSError(ENOSPC)``) leaves the source intact and cleans up
     ``dest.tmp``.
  5. **Hash verification** (US2.2): the cross-fs copy re-hashes the
     written bytes and raises ``MoveError(rejection_reason=
     'move:copy_hash_mismatch')`` on mismatch — the source is
     preserved so the orchestrator can retry.

Source deletion (``move_and_remove`` lifecycle policy) is the
**orchestrator's** concern: the library row carries the
``lifecycle_policy`` value the LIFECYCLE step consults. This step
focuses on landing ``dest`` correctly.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from romarr.identification.hasher import Hasher
from romarr.importer.errors import MoveError
from romarr.importer.types import RejectionReason


@dataclass(frozen=True)
class MoveResult:
    """Outcome of a successful :func:`move_atomic`.

    ``coalesced`` is ``True`` when ``dest`` already existed with the
    expected SHA-1 — the import call was a no-op (FR-025). The
    audit row records the coalesce so the operator can see "5
    callers all tried; 1 actually moved, 4 coalesced".
    """

    dest: Path
    coalesced: bool
    used_hardlink: bool
    bytes_copied: int


# ---------------------------------------------------------------------------
# Sync helpers (run inside ``asyncio.to_thread``)


def _sync_sha1(path: Path) -> str:
    return Hasher().hash_path(path).sha1


def _sync_copy_and_verify(
    source: Path, tmp_dest: Path, expected_sha1: str
) -> int:
    """Copy ``source`` → ``tmp_dest`` preserving mtime, then verify
    SHA-1. Cleans up ``tmp_dest`` on any failure path so a partial
    file never lands. Returns the number of bytes copied."""
    tmp_dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, tmp_dest)
        actual = _sync_sha1(tmp_dest)
        if actual != expected_sha1:
            raise MoveError(
                f"copy hash mismatch for {source.name}: "
                f"expected {expected_sha1[:8]}…, got {actual[:8]}…",
                rejection_reason=RejectionReason.MOVE_HASH_MISMATCH.value,
            )
        return tmp_dest.stat().st_size
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp_dest.unlink()
        raise


# ---------------------------------------------------------------------------
# Async public API


async def move_atomic(
    *,
    source: Path,
    dest: Path,
    expected_sha1: str,
    force: bool = False,
) -> MoveResult:
    """Land ``source`` at ``dest`` atomically. See module docstring
    for the full contract."""
    expected_sha1 = expected_sha1.lower()

    # Step 1: idempotent re-import.
    if dest.exists():
        existing_sha1 = await asyncio.to_thread(_sync_sha1, dest)
        if existing_sha1.lower() == expected_sha1:
            return MoveResult(
                dest=dest,
                coalesced=True,
                used_hardlink=False,
                bytes_copied=0,
            )
        # Step 2: destination collision.
        if not force:
            raise MoveError(
                f"destination {dest} already exists with different SHA-1",
                rejection_reason=RejectionReason.DESTINATION_COLLISION.value,
            )
        # force=True ⇒ unlink the existing file so the hardlink /
        # rename below has a clean slot.
        with contextlib.suppress(FileNotFoundError):
            dest.unlink()

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Step 3: hardlink-first.
    try:
        await asyncio.to_thread(os.link, source, dest)
        return MoveResult(
            dest=dest,
            coalesced=False,
            used_hardlink=True,
            bytes_copied=0,
        )
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            # Anything other than cross-fs surfaces immediately:
            # ENOSPC, EACCES, EPERM, etc. The source is untouched.
            raise _wrap_move_oserror(exc) from exc

    # Step 4: cross-fs copy + verify + atomic rename.
    tmp_dest = dest.with_name(dest.name + ".tmp")
    try:
        bytes_copied = await asyncio.to_thread(
            _sync_copy_and_verify, source, tmp_dest, expected_sha1
        )
    except MoveError:
        raise
    except OSError as exc:
        raise _wrap_move_oserror(exc) from exc

    try:
        await asyncio.to_thread(os.replace, tmp_dest, dest)
    except OSError as exc:
        with contextlib.suppress(FileNotFoundError):
            tmp_dest.unlink()
        raise _wrap_move_oserror(exc) from exc

    return MoveResult(
        dest=dest,
        coalesced=False,
        used_hardlink=False,
        bytes_copied=bytes_copied,
    )


def _wrap_move_oserror(exc: OSError) -> MoveError:
    """Translate an :class:`OSError` to a :class:`MoveError` with
    the right structured ``rejection_reason``. Any other OSError
    surfaces with the generic ``move:failed`` reason so the audit
    row still carries a structured code."""
    if exc.errno == errno.ENOSPC:
        return MoveError(
            f"disk full while writing {exc.filename!r}",
            rejection_reason=RejectionReason.MOVE_DISK_FULL.value,
        )
    if exc.errno in (errno.EACCES, errno.EPERM):
        return MoveError(
            f"permission denied: {exc}",
            rejection_reason=RejectionReason.MOVE_PERMISSION_ERROR.value,
        )
    return MoveError(
        f"move failed: {exc}",
        rejection_reason=RejectionReason.MOVE_FAILED.value,
    )


__all__ = ["MoveResult", "move_atomic"]
