"""Polling watcher tests (spec 008 T014 / T015 / T016).

Spec contracts:

* T014 — polls every 30 s. Validated against the watcher's
  ``tick()`` cadence + a tunable interval (so the test isn't 30 s
  long; the fast interval pins the loop's cycle).
* T015 — filters by tag. Items with ``imported=True`` (qBit's
  ``romarr-imported`` tag set) are skipped. Items already-seen this
  run are also skipped.
* T016 — isolates a failing client. When one client raises during
  ``list_managed_downloads``, the watcher logs and continues with the
  remaining clients on the same tick.

The tests use stub :class:`DownloadClient` shapes that satisfy the
ABC contract surface needed by :class:`WatcherLoop` only — full
ABC compliance isn't necessary because the watcher only calls
``list_managed_downloads``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest

from romarr.downloaders.types import ManagedDownload
from romarr.importer.steps.watch import WatcherLoop


class _FakeClient:
    """Minimal client stub — only ``list_managed_downloads`` is read.

    ``raises`` makes the call fail (T016). ``items`` is the canned
    return value otherwise. ``call_count`` lets tests assert poll
    cadence (T014).
    """

    def __init__(
        self,
        *,
        client_id: int,
        items: list[ManagedDownload],
        raises: type[BaseException] | None = None,
    ) -> None:
        self.client_id = client_id
        self._items = items
        self._raises = raises
        self.call_count = 0

    async def list_managed_downloads(self) -> list[ManagedDownload]:
        self.call_count += 1
        if self._raises is not None:
            raise self._raises("fake client failure")
        return list(self._items)


def _make(client_id: int, native_id: str, *, imported: bool = False) -> ManagedDownload:
    return ManagedDownload(
        client_id=client_id,
        client_native_id=native_id,
        name=f"download-{native_id}",
        save_path=f"/downloads/{native_id}",
        imported=imported,
    )


@pytest.mark.asyncio
async def test_polls_every_30s() -> None:
    """T014 — the watcher fires per-tick on the configured interval.

    The 30 s default would make the test slow; we pin the interval to
    50 ms and assert that two ticks land within ~ 200 ms. The cadence
    contract is structurally pinned (loop-then-wait-interval) — the
    fast-interval check just proves the loop actually loops.
    """
    client = _FakeClient(client_id=1, items=[])
    dispatched: list[ManagedDownload] = []

    async def get_clients() -> Sequence[Any]:
        return [client]

    async def dispatcher(item: ManagedDownload) -> None:
        dispatched.append(item)

    loop = WatcherLoop(
        get_clients=get_clients,
        dispatcher=dispatcher,
        interval_seconds=0.05,
    )
    await loop.start()
    try:
        # Wait long enough for at least 2 polls at 50 ms cadence.
        await asyncio.sleep(0.18)
    finally:
        await loop.stop()

    assert client.call_count >= 2
    # Default interval constant exposes the FR-001 30 s cadence.
    from romarr.importer.steps.watch import DEFAULT_INTERVAL_SECONDS

    assert DEFAULT_INTERVAL_SECONDS == 30


@pytest.mark.asyncio
async def test_filters_by_tag() -> None:
    """T015 — items already carrying ``romarr-imported`` are skipped.

    The watcher's dedup pipeline:
      1. Skip items with ``imported=True`` (already tagged).
      2. Skip items the loop has already dispatched this run.

    Both layers must hold; a re-tick on the same items must dispatch
    nothing.
    """
    items = [
        _make(1, "abc", imported=False),
        _make(1, "def", imported=True),  # already imported
        _make(1, "ghi", imported=False),
    ]
    client = _FakeClient(client_id=1, items=items)
    dispatched: list[ManagedDownload] = []

    async def get_clients() -> Sequence[Any]:
        return [client]

    async def dispatcher(item: ManagedDownload) -> None:
        dispatched.append(item)

    loop = WatcherLoop(
        get_clients=get_clients, dispatcher=dispatcher, interval_seconds=0.01
    )

    # One manual tick — assert imported items are filtered out.
    n = await loop.tick()
    assert n == 2
    assert {d.client_native_id for d in dispatched} == {"abc", "ghi"}

    # Second tick on the same data — already-seen dedup must hold.
    n2 = await loop.tick()
    assert n2 == 0
    assert len(dispatched) == 2


@pytest.mark.asyncio
async def test_isolates_failing_client() -> None:
    """T016 — when one client raises, others on the same tick proceed.

    Per FR-019 the watcher must not let one misbehaving client drop
    the whole pipeline. The failing client logs its exception and the
    loop iterates to the next client without re-raising.
    """
    failing = _FakeClient(client_id=1, items=[], raises=ConnectionError)
    healthy = _FakeClient(
        client_id=2,
        items=[
            _make(2, "good-1", imported=False),
            _make(2, "good-2", imported=False),
        ],
    )

    async def get_clients() -> Sequence[Any]:
        return [failing, healthy]

    dispatched: list[ManagedDownload] = []

    async def dispatcher(item: ManagedDownload) -> None:
        dispatched.append(item)

    loop = WatcherLoop(
        get_clients=get_clients, dispatcher=dispatcher, interval_seconds=0.01
    )

    # The failing client must not abort the tick.
    n = await loop.tick()
    assert n == 2
    assert {d.client_id for d in dispatched} == {2}
    assert {d.client_native_id for d in dispatched} == {"good-1", "good-2"}

    # Both clients were polled — fault isolation is per-client, not
    # per-loop-cycle.
    assert failing.call_count == 1
    assert healthy.call_count == 1
