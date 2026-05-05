"""Lifecycle-action tests (T073-T076, FR-029 / FR-030)."""

from __future__ import annotations

import asyncio

import pytest

from romarr.downloaders.base import DownloadClient
from romarr.downloaders.types import (
    DownloadStatus,
    NzbUrl,
    SourceKind,
    TorrentMagnet,
    TorrentUrl,
)
from romarr.importer.steps.lifecycle import apply_lifecycle
from romarr.importer.types import LifecycleAction


class _FakeDownloadClient(DownloadClient):
    """Records every method call so tests can assert ordering."""

    SUPPORTED_KINDS: tuple[SourceKind, ...] = (SourceKind.TORRENT,)

    def __init__(self) -> None:
        super().__init__(client_id=1, name="fake")
        self.tagged: list[str] = []
        self.removed: list[tuple[str, bool]] = []

    async def test_connection(self) -> str:
        return "ok"

    async def add_torrent(
        self,
        source: TorrentMagnet | TorrentUrl,
        *,
        category: str = "romarr",
        tags: list[str] | None = None,
    ) -> str:
        return "fake-id"

    async def add_nzb(
        self, source: NzbUrl, *, category: str = "romarr"
    ) -> str:
        return "fake-id"

    async def get_status(self, client_native_id: str) -> DownloadStatus:
        return DownloadStatus(
            native_id=client_native_id,
            state="seeding",
            progress=1.0,
            label="romarr",
            tags=("romarr",),
        )

    async def remove(
        self, client_native_id: str, *, delete_files: bool
    ) -> None:
        self.removed.append((client_native_id, delete_files))

    async def set_imported_tag(self, client_native_id: str) -> None:
        self.tagged.append(client_native_id)

    async def ensure_category(self) -> None:
        pass

    async def list_managed_downloads(self) -> list:
        return []


def _action(kind: str) -> LifecycleAction:
    return LifecycleAction(
        kind=kind,  # type: ignore[arg-type]
        download_client_id=1,
        download_client_native_id="info-hash-abc",
    )


# ---------------------------------------------------------------------------
# T073 — tag_imported tags but does not remove
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tag_imported_tags_only() -> None:
    client = _FakeDownloadClient()
    task = await apply_lifecycle(
        action=_action("tag_imported"), client=client
    )
    assert task is None
    assert client.tagged == ["info-hash-abc"]
    assert client.removed == []


# ---------------------------------------------------------------------------
# T074 — schedule_remove fires after grace; orchestrator returns first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_remove_fires_after_grace() -> None:
    """``schedule_remove`` returns immediately with a Task; the
    actual removal fires when the grace window elapses (FR-029)."""
    client = _FakeDownloadClient()
    task = await apply_lifecycle(
        action=_action("schedule_remove"),
        client=client,
        grace_seconds=0.05,  # tiny grace for the test
    )
    assert isinstance(task, asyncio.Task)
    # Tag fires synchronously before apply_lifecycle returns.
    assert client.tagged == ["info-hash-abc"]
    # Removal hasn't fired yet — the task is still sleeping.
    assert client.removed == []

    await task
    assert client.removed == [("info-hash-abc", True)]


@pytest.mark.asyncio
async def test_schedule_remove_does_not_block_completion() -> None:
    """FR-030: the orchestrator's ImportOutcome is published BEFORE
    the grace window completes. We model that by measuring the
    time apply_lifecycle takes — it must be << grace_seconds."""
    import time

    client = _FakeDownloadClient()
    started = time.perf_counter()
    task = await apply_lifecycle(
        action=_action("schedule_remove"),
        client=client,
        grace_seconds=10.0,  # long grace
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0  # apply_lifecycle returned in < 1s
    assert isinstance(task, asyncio.Task)
    # Cancel the long-running task so the test exits cleanly.
    task.cancel()
    with pytest.raises((asyncio.CancelledError, BaseException)) as exc:
        await task
    assert exc.type in (asyncio.CancelledError,) or isinstance(
        exc.value, asyncio.CancelledError
    )


# ---------------------------------------------------------------------------
# T075 — copy_and_keep is a noop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_noop_neither_tags_nor_removes() -> None:
    client = _FakeDownloadClient()
    task = await apply_lifecycle(action=_action("noop"), client=client)
    assert task is None
    assert client.tagged == []
    assert client.removed == []


# ---------------------------------------------------------------------------
# Defensive: unknown kind surfaces a ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_action_kind_raises() -> None:
    client = _FakeDownloadClient()
    # Bypass Pydantic to construct a bogus kind for the dispatcher.
    bogus = LifecycleAction.model_construct(
        kind="weird",  # type: ignore[arg-type]
        download_client_id=1,
        download_client_native_id="abc",
        not_before=None,
    )
    with pytest.raises(ValueError, match="unknown lifecycle action kind"):
        await apply_lifecycle(action=bogus, client=client)
