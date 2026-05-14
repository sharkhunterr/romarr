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

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from romarr.domain.models import RomPack
from romarr.downloaders.factory import build_client_from_row
from romarr.downloaders.models import DownloadClient as DownloadClientRow
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.rom_packs.ingest import ingest_rom_pack

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from romarr.downloaders.base import DownloadClient
    from romarr.downloaders.types import ManagedDownload
    from romarr.notifications.channel import EventChannel

logger = logging.getLogger(__name__)


def build_managed_download_dispatcher(
    sessionmaker: async_sessionmaker,
    *,
    event_channel: EventChannel | None = None,
) -> Callable[[ManagedDownload], Awaitable[None]]:
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

    async def dispatch(item: ManagedDownload) -> None:
        save_path = item.save_path or ""
        if not save_path:
            logger.warning(
                "watcher_dispatch.skip_empty_save_path "
                "client_id=%s native_id=%s",
                item.client_id,
                item.client_native_id,
            )
            return

        # Slice 463 — a completed download bound to a ``grab``-
        # sourced RomPack is a ROM *content pack*, not a single
        # release: route it to the pack ingest pipeline instead
        # of ``run_import``. The helper settles the queue_entry
        # and fires the ingest as a detached task; returning
        # True means "handled, don't fall through".
        if await _maybe_route_to_rom_pack(sessionmaker, item, save_path):
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
            from romarr.importer.models import ImportHistory

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

            # Slice 459 — double-dispatch guard. If the source file
            # is already gone AND a prior import for this exact
            # (client, native_id) pair succeeded, a previous
            # dispatch already consumed it (extracted + moved). The
            # second dispatch — watcher re-tick after a restart,
            # reconciler recovery, manual re-trigger — must NOT
            # raise FileNotFoundError and flip the queue_entry to
            # ``failed``. Treat it as the no-op coalesced success
            # it really is: settle the queue_entry clean and
            # return.
            if not Path(save_path).exists():
                prior_ok = (
                    await lookup_session.execute(
                        _select(ImportHistory.id)
                        .where(
                            ImportHistory.download_client_id
                            == item.client_id,
                            ImportHistory.download_client_native_id
                            == item.client_native_id,
                            ImportHistory.success.is_(True),
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if prior_ok is not None:
                    logger.info(
                        "watcher_dispatch.already_imported "
                        "client_id=%s native_id=%s — source gone, "
                        "prior import #%s succeeded; settling clean",
                        item.client_id,
                        item.client_native_id,
                        prior_ok,
                    )
                    await _settle_queue_entry(
                        session=lookup_session,
                        client_id=item.client_id,
                        native_id=item.client_native_id,
                        title=item.name,
                        success=True,
                        error_msg=None,
                    )
                    await lookup_session.commit()
                    return

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
            success: bool
            error_msg: str | None
            try:
                outcome = await run_import(
                    context,
                    session=session,
                    event_channel=event_channel,
                )
                success = outcome.success
                error_msg = outcome.error_msg
            except Exception as exc:
                # Slice 390 — an *uncaught* run_import failure
                # (PermissionError on the library tree, DB error,
                # etc.) used to leave the queue_entry frozen at
                # ``completed`` forever and the operator saw
                # nothing in the UI. Treat it as a hard failure
                # for queue purposes — the dispatcher's ``raise``
                # below still notifies the watcher, but the queue
                # row gets the truthful ``state='failed'`` plus
                # a class-name+message so the operator can act
                # without digging into logs.
                success = False
                error_msg = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    "watcher_dispatch.run_import_failed "
                    "client_id=%s native_id=%s",
                    item.client_id,
                    item.client_native_id,
                )

            # Slice 384/389 — settle the originating queue_entry.
            # On success the row vanishes; on failure it flips to
            # ``state='failed'`` (or a synthetic row gets inserted
            # when no queue_entry matches the (client_id,
            # native_id) pair).
            try:
                await _settle_queue_entry(
                    session=session,
                    client_id=item.client_id,
                    native_id=item.client_native_id,
                    title=item.name,
                    success=success,
                    error_msg=error_msg,
                )
            except Exception:
                logger.exception(
                    "watcher_dispatch.settle_queue_entry_failed "
                    "client_id=%s native_id=%s",
                    item.client_id,
                    item.client_native_id,
                )

            # We deliberately don't re-raise even on the
            # unstructured exception path: the queue_entry is now
            # the authoritative surface for the operator, and the
            # watcher's per-item exception handler would just log
            # the same thing twice. The next tick re-evaluates
            # the same download (no ``romarr-imported`` tag yet)
            # so a transient cause (permissions just chowned,
            # disk just remounted) auto-recovers.

    return dispatch


async def _settle_queue_entry(
    *,
    session: AsyncSession,
    client_id: int,
    native_id: str,
    title: str | None,
    success: bool,
    error_msg: str | None,
) -> None:
    """Reconcile the queue_entry mirror with the import outcome.

    Success + matching row → delete the row so the
    Activity → Queue tab only keeps in-flight or failed work
    visible. Success + no matching row → no-op (nothing to
    surface).

    Failure + matching row → set ``state='failed'`` + populate
    ``error_msg`` so the queue list surfaces the rejection
    reason (e.g. ``extract:bad-archive``, ``match:no_game``).
    Failure + no matching row → insert a synthetic row in the
    same state so the operator sees the failure even when the
    download didn't go through ``manual_grab`` (Sonarr-compat
    add, hash drift, etc.).
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
        if success:
            return
        session.add(
            QueueEntry(
                download_client_id=client_id,
                download_client_native_id=native_id,
                title=title,
                state="failed",
                progress=1.0,
                error_msg=error_msg or "import_failed",
            )
        )
        await session.commit()
        return
    if success:
        await session.delete(row)
    else:
        row.state = "failed"
        row.error_msg = error_msg or "import_failed"
    await session.commit()


async def _maybe_route_to_rom_pack(
    sessionmaker: async_sessionmaker,
    item: ManagedDownload,
    save_path: str,
) -> bool:
    """Route a completed download to the ROM-pack ingest pipeline
    when it's bound to a ``grab``-sourced :class:`RomPack`.

    Returns ``True`` when the download was a pack (handled —
    caller must not run the single-file importer), ``False``
    when it's an ordinary release.

    The download itself is complete (the watcher only dispatches
    finished items), so the originating ``queue_entry`` is
    settled as a success straight away — the pack's own
    ``status`` field is the channel the Content Packs page polls
    for the download-extract-import progress that follows.

    Idempotent: only a pack still in ``pending`` triggers an
    ingest. A watcher re-tick after a restart sees a non-pending
    status and just re-settles the queue_entry.
    """
    async with sessionmaker() as session:
        pack = (
            await session.execute(
                select(RomPack).where(
                    RomPack.source_kind == "grab",
                    RomPack.download_client_id == item.client_id,
                    RomPack.download_client_native_id
                    == item.client_native_id,
                )
            )
        ).scalar_one_or_none()
        if pack is None:
            return False

        pack_id = pack.id
        already_started = pack.status != "pending"
        if not already_started:
            pack.downloaded_path = save_path
            await session.commit()

        try:
            await _settle_queue_entry(
                session=session,
                client_id=item.client_id,
                native_id=item.client_native_id,
                title=item.name,
                success=True,
                error_msg=None,
            )
        except Exception:
            logger.exception(
                "watcher_dispatch.rom_pack.settle_failed "
                "pack_id=%s client_id=%s native_id=%s",
                pack_id,
                item.client_id,
                item.client_native_id,
            )

    if already_started:
        logger.info(
            "watcher_dispatch.rom_pack.already_handled pack_id=%s "
            "client_id=%s native_id=%s",
            pack_id,
            item.client_id,
            item.client_native_id,
        )
        return True

    # Fire the ingest detached — a multi-GB pack must not block
    # the watcher's serial per-item dispatch loop.
    async def _run() -> None:
        try:
            await ingest_rom_pack(
                sessionmaker=sessionmaker, rom_pack_id=pack_id
            )
        except Exception:
            logger.exception(
                "watcher_dispatch.rom_pack.ingest_crashed pack_id=%s",
                pack_id,
            )

    asyncio.get_running_loop().create_task(_run())
    logger.info(
        "watcher_dispatch.rom_pack.ingest_started pack_id=%s "
        "client_id=%s native_id=%s",
        pack_id,
        item.client_id,
        item.client_native_id,
    )
    return True


def build_get_enabled_clients(
    sessionmaker: async_sessionmaker,
) -> Callable[[], Awaitable[list[DownloadClient]]]:
    """Build a ``get_clients`` callable for the watcher loop.

    Each call queries DB for enabled rows + builds instances. Build
    failures (decryption errors, missing credentials, unknown type)
    are logged and the row is skipped — the watcher proceeds with
    the remaining clients.
    """

    async def get_clients() -> list[DownloadClient]:
        async with sessionmaker() as session:
            rows = (
                await session.execute(
                    select(DownloadClientRow).where(
                        DownloadClientRow.enabled.is_(True)
                    )
                )
            ).scalars().all()

        out: list[DownloadClient] = []
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
