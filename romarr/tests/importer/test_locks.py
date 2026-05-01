"""ImportLockManager tests (T012, FR-033 / FR-034)."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from romarr.importer.errors import LockTimeout
from romarr.importer.locks import ImportLockManager


@pytest.mark.asyncio
async def test_distinct_keys_run_in_parallel() -> None:
    """Two acquirers on different (release_id, sha1) keys run
    concurrently — there's no global lock."""
    manager = ImportLockManager(timeout_s=2.0)
    inside_a = asyncio.Event()
    inside_b = asyncio.Event()

    async def hold_a() -> None:
        async with manager.acquire(release_id=1, sha1="a" * 40):
            inside_a.set()
            await asyncio.sleep(0.05)

    async def hold_b() -> None:
        async with manager.acquire(release_id=2, sha1="b" * 40):
            inside_b.set()
            await asyncio.sleep(0.05)

    await asyncio.gather(hold_a(), hold_b())
    assert inside_a.is_set()
    assert inside_b.is_set()


@pytest.mark.asyncio
async def test_same_key_serialises() -> None:
    """Two acquirers on the same (release_id, sha1) serialise —
    the second only enters once the first releases."""
    manager = ImportLockManager(timeout_s=2.0)
    sequence: list[str] = []

    async def first() -> None:
        async with manager.acquire(release_id=1, sha1="a" * 40):
            sequence.append("first-enter")
            await asyncio.sleep(0.05)
            sequence.append("first-exit")

    async def second() -> None:
        await asyncio.sleep(0.01)  # let `first` enter first
        async with manager.acquire(release_id=1, sha1="a" * 40):
            sequence.append("second-enter")

    await asyncio.gather(first(), second())
    assert sequence == ["first-enter", "first-exit", "second-enter"]


@pytest.mark.asyncio
async def test_timeout_raises_lock_timeout() -> None:
    """When a holder takes longer than the configured timeout,
    the second acquirer raises :class:`LockTimeout`."""
    manager = ImportLockManager(timeout_s=0.1)

    async def hold_forever() -> None:
        async with manager.acquire(release_id=1, sha1="a" * 40):
            await asyncio.sleep(1.0)

    holder_task = asyncio.create_task(hold_forever())
    await asyncio.sleep(0.02)  # let the holder acquire

    with pytest.raises(LockTimeout):
        async with manager.acquire(release_id=1, sha1="a" * 40):
            pytest.fail("should not have entered the lock")

    holder_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await holder_task


@pytest.mark.asyncio
async def test_lock_released_on_exception() -> None:
    """An exception inside the ``async with`` block must still
    release the lock so a subsequent caller can proceed."""
    manager = ImportLockManager(timeout_s=1.0)

    class _BoomError(RuntimeError):
        pass

    with pytest.raises(_BoomError):
        async with manager.acquire(release_id=1, sha1="a" * 40):
            raise _BoomError("step failed mid-pipeline")

    # Second acquirer would block forever (or time out) if the
    # first didn't release.
    async with manager.acquire(release_id=1, sha1="a" * 40):
        pass
