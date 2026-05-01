"""Per-(release_id, sha1) advisory locks (FR-033 / FR-034).

The orchestrator serialises concurrent imports targeting the same
``(release_id, sha1)`` key with an in-process advisory lock so a
double-fire of the post-download-complete webhook + the polling
watcher can't both create Dump rows for the same file. The first
holder runs the full pipeline; the second short-circuits with
``coalesced=true`` once it sees the Dump now exists.

The lock is **in-process only** — it doesn't survive a restart
and it doesn't span uvicorn workers. Multi-worker deployments
serialise on the DB unique constraint on ``Dump.path`` instead;
the in-process lock is the fast path that avoids the IntegrityError
round-trip in the common case.

The 60-second timeout (FR-034) prevents a hung step from blocking
the rest of the pipeline forever; on timeout the caller raises
:class:`LockTimeout` and records
``rejection_reason='lock:timeout'``.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from romarr.importer.errors import LockTimeout

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


_DEFAULT_TIMEOUT_S = 60.0


class ImportLockManager:
    """Lazy registry of per-key :class:`asyncio.Lock` instances.

    A new lock is allocated the first time a key is acquired; it
    stays in the registry for the rest of the process lifetime so
    repeat acquisitions are cheap. We don't garbage-collect locks —
    the key cardinality is bounded by the number of (release, sha1)
    pairs the operator has, which is small.
    """

    def __init__(self, *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}
        # Guard the dict itself so concurrent first-time acquisitions
        # of distinct keys don't race each other.
        self._registry_lock = asyncio.Lock()

    async def _get(self, key: tuple[int, str]) -> asyncio.Lock:
        async with self._registry_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    @asynccontextmanager
    async def acquire(
        self, *, release_id: int, sha1: str
    ) -> AsyncIterator[None]:
        """Acquire the lock for ``(release_id, sha1)``.

        Raises :class:`LockTimeout` if the lock can't be obtained
        within ``timeout_s``. The release happens automatically on
        context exit.
        """
        key = (release_id, sha1)
        lock = await self._get(key)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=self._timeout_s)
        except TimeoutError as exc:
            raise LockTimeout(
                f"could not acquire import lock for "
                f"release_id={release_id} sha1={sha1[:8]}… "
                f"within {self._timeout_s} s"
            ) from exc
        try:
            yield
        finally:
            lock.release()


__all__ = ["ImportLockManager"]
