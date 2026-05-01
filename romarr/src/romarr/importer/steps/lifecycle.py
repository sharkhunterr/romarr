"""Lifecycle-action step (FR-029 / FR-030 / pipeline step 12).

After a successful import, the importer dispatches the library's
configured lifecycle action against the originating download
client:

  * ``tag_imported`` — tag the download with ``romarr-imported`` so
    spec 005's lifecycle filter no longer surfaces it on the next
    poll. Used by the ``hardlink_and_seed`` library policy.
  * ``schedule_remove`` — first tag, then schedule a delayed
    ``client.remove(client_native_id, delete_files=True)`` after
    the configured grace window (default 5 min, FR-029). Used by
    ``move_and_remove``. The schedule fires in a background
    asyncio task so the orchestrator returns the
    :class:`ImportOutcome` to the caller immediately (FR-030).
  * ``noop`` — neither tag nor remove. Used by the
    ``copy_and_keep`` policy when the operator wants the
    originating download to remain untouched.

The schedule-remove task is **fire-and-forget** by design.
``apply_lifecycle`` returns the :class:`asyncio.Task` it created
(or ``None`` for tag-only / noop) so tests can ``await`` it.
Production callers never await — the task lives until either the
grace window completes or the asyncio loop shuts down.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from romarr.downloaders.base import DownloadClient
    from romarr.importer.types import LifecycleAction


_DEFAULT_GRACE_SECONDS = 300.0


async def apply_lifecycle(
    *,
    action: LifecycleAction,
    client: DownloadClient,
    grace_seconds: float = _DEFAULT_GRACE_SECONDS,
) -> asyncio.Task[None] | None:
    """Dispatch ``action`` against ``client``.

    Returns the scheduled-remove :class:`asyncio.Task` for the
    ``schedule_remove`` kind so tests can ``await`` it; returns
    ``None`` for ``tag_imported`` and ``noop``.

    Per FR-030 the orchestrator MUST NOT block on the grace-window
    sleep — the calling task must already have published the
    ``ImportOutcome`` by the time we get here. We honour that by
    backgrounding the sleep + remove via
    ``asyncio.create_task``.
    """
    if action.kind == "noop":
        return None

    # Both ``tag_imported`` and ``schedule_remove`` start by
    # tagging — the tag is what stops spec 005's lifecycle filter
    # from re-surfacing the download on the next poll.
    await client.set_imported_tag(action.download_client_native_id)

    if action.kind == "tag_imported":
        return None

    if action.kind == "schedule_remove":
        return asyncio.create_task(
            _delayed_remove(
                client=client,
                native_id=action.download_client_native_id,
                grace_seconds=grace_seconds,
            )
        )

    # Defensive: every kind covered above; type-check guards this
    # but if a new variant lands without the dispatcher being
    # updated, fail loudly rather than silently noop.
    raise ValueError(
        f"unknown lifecycle action kind: {action.kind!r}"
    )


async def _delayed_remove(
    *,
    client: DownloadClient,
    native_id: str,
    grace_seconds: float,
) -> None:
    """Sleep ``grace_seconds`` then remove the download. Files are
    deleted alongside the download row because the importer has
    already hardlinked / copied the bytes into the library — the
    seedable copy lives at the library destination, not the
    download client's working directory."""
    await asyncio.sleep(grace_seconds)
    await client.remove(native_id, delete_files=True)


__all__ = ["apply_lifecycle"]
