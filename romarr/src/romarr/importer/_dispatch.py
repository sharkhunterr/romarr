"""Production wiring for the importer's ``run_import`` entry point.

The orchestrator owns the import contract; this module owns the two
glue callables the runtime needs to actually invoke it:

* :func:`build_managed_download_dispatcher` — turns a
  :class:`ManagedDownload` into an :class:`ImportContext` and runs
  the orchestrator with a fresh session. Used by both the watcher
  loop (via :class:`WatcherLoop.dispatcher`) and the webhook
  surface (via :func:`romarr.importer.webhook.configure_dispatcher`).

* :func:`build_get_enabled_clients` — returns an async closure that
  loads every enabled :class:`DownloadClient` row from DB and builds
  the corresponding implementation instances. Re-evaluated on every
  watcher tick so dynamic add/remove of clients takes effect on the
  next poll without restarting the lifespan.

The helpers are pure factories — neither holds DB state directly.
The session factory passed in owns the DB engine; on shutdown the
engine.dispose() in ``api/app.py`` flushes everything cleanly.

Failure semantics (all swallowed at this boundary):
* DB row → client build failures: the row is logged and skipped
  rather than raised, so a single misconfigured row doesn't take
  down the whole watcher cycle (FR-019 fault isolation).
* Dispatcher invocation failures: re-raised so the watcher's
  per-item exception handler catches and logs them with the right
  (client_id, native_id) context.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from romarr.downloaders.factory import build_client_from_row
from romarr.downloaders.models import DownloadClient as DownloadClientRow
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from romarr.downloaders.base import DownloadClient
    from romarr.downloaders.types import ManagedDownload
    from romarr.notifications.channel import EventChannel

logger = logging.getLogger(__name__)


def build_managed_download_dispatcher(
    sessionmaker: "async_sessionmaker",
    *,
    event_channel: "EventChannel | None" = None,
) -> Callable[["ManagedDownload"], Awaitable[None]]:
    """Build a watcher-compatible dispatcher closure over ``sessionmaker``.

    The returned callable takes a :class:`ManagedDownload`, opens a
    fresh session, builds an :class:`ImportContext` carrying the
    client + native id pair so the import history row tracks the
    download's origin, and invokes :func:`run_import`.

    The watcher uses ``imported_via="automatic"`` (it polls clients
    on a 30 s cadence with no operator action); the webhook uses
    ``imported_via="webhook"`` so the audit chain distinguishes
    the two operator-invisible signal paths.
    """

    async def dispatch(item: "ManagedDownload") -> None:
        save_path = item.save_path or ""
        if not save_path:
            logger.warning(
                "watcher_dispatch.skip_empty_save_path "
                "client_id=%s native_id=%s",
                item.client_id,
                item.client_native_id,
            )
            return

        # Look up the parent queue_entry so we thread the
        # operator's pre-resolved game / release ids into the
        # import. Skips the filename-fuzzy game-match step when
        # we already know the answer from the manual grab.
        pre_game_id: int | None = None
        pre_release_id: int | None = None
        async with sessionmaker() as lookup_session:
            from sqlalchemy import select as _select

            from romarr.api.models import QueueEntry

            qrow = (
                await lookup_session.execute(
                    _select(QueueEntry).where(
                        QueueEntry.download_client_id == item.client_id,
                        QueueEntry.download_client_native_id
                        == item.client_native_id,
                    )
                )
            ).scalar_one_or_none()
            if qrow is not None:
                pre_game_id = qrow.game_id
                pre_release_id = qrow.release_id

        context = ImportContext(
            source_path=Path(save_path),
            correlation_id=uuid4(),
            imported_via="automatic",
            download_client_id=item.client_id,
            download_client_native_id=item.client_native_id,
            pre_matched_game_id=pre_game_id,
            pre_matched_release_id=pre_release_id,
        )

        async with sessionmaker() as session:
            try:
                outcome = await run_import(
                    context,
                    session=session,
                    event_channel=event_channel,
                )
            except Exception:
                logger.exception(
                    "watcher_dispatch.run_import_failed "
                    "client_id=%s native_id=%s",
                    item.client_id,
                    item.client_native_id,
                )
                raise

            # Slice 384 — settle the originating queue_entry. On
            # success the row vanishes (Activity → Queue is for
            # in-flight or failed work; the audit trail lives in
            # ``import_history``). On failure the row flips to
            # ``failed`` with the rejection reason on
            # ``error_msg`` so the operator can see + retry.
            try:
                await _settle_queue_entry(
                    session=session,
                    client_id=item.client_id,
                    native_id=item.client_native_id,
                    success=outcome.success,
                    error_msg=outcome.error_msg,
                )
            except Exception:
                logger.exception(
                    "watcher_dispatch.settle_queue_entry_failed "
                    "client_id=%s native_id=%s",
                    item.client_id,
                    item.client_native_id,
                )

    return dispatch


async def _settle_queue_entry(
    *,
    session: "AsyncSession",
    client_id: int,
    native_id: str,
    success: bool,
    error_msg: str | None,
) -> None:
    """Reconcile the queue_entry mirror with the import outcome.

    Success → delete the row so the Activity → Queue tab only
    keeps in-flight or failed work visible.

    Failure → set ``state='failed'`` + populate ``error_msg`` so
    the operator's queue list surfaces the rejection reason
    (e.g. ``extract:bad-archive``, ``match:no_game``) without
    needing to dig into history.
    """
    from sqlalchemy import select as _select

    from romarr.api.models import QueueEntry

    row = (
        await session.execute(
            _select(QueueEntry).where(
                QueueEntry.download_client_id == client_id,
                QueueEntry.download_client_native_id == native_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return
    if success:
        await session.delete(row)
    else:
        row.state = "failed"
        row.error_msg = error_msg or "import_failed"
    await session.commit()


def build_get_enabled_clients(
    sessionmaker: "async_sessionmaker",
) -> Callable[[], Awaitable[list["DownloadClient"]]]:
    """Build a ``get_clients`` callable for the watcher loop.

    Each call queries DB for enabled rows + builds instances. Build
    failures (decryption errors, missing credentials, unknown type)
    are logged and the row is skipped — the watcher proceeds with
    the remaining clients.
    """

    async def get_clients() -> list["DownloadClient"]:
        async with sessionmaker() as session:
            rows = (
                await session.execute(
                    select(DownloadClientRow).where(
                        DownloadClientRow.enabled.is_(True)
                    )
                )
            ).scalars().all()

        out: list["DownloadClient"] = []
        for row in rows:
            try:
                out.append(build_client_from_row(row))
            except Exception:
                logger.exception(
                    "watcher.client_build_failed id=%s name=%s type=%s",
                    row.id,
                    row.name,
                    row.type,
                )
        return out

    return get_clients


__all__ = [
    "build_get_enabled_clients",
    "build_managed_download_dispatcher",
]
