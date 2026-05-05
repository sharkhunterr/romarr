"""Full filesystem scan — discover and link existing ROMs (spec 009 — Phase 6 SCAN-FULL).

Per FR-009 the scanner walks ``library.path`` recursively and
hashes every file matching a known platform-format extension.
Per FR-010 a re-scan is idempotent: files whose ``(path, size)``
already match a Dump are skipped without rehashing. Per FR-011
Dumps whose file no longer exists at their stored path are
flagged orphaned: their parent Release transitions to
``status='wanted'`` and a structured warning is emitted. Per
FR-012 long scans publish progress events every 100 files.

The current slice ships the **discovery + idempotent re-scan +
orphan sweep + link-by-hash** path. Creating new Releases for
unmatched files (FR-014) requires the importer's full
identification cascade and lives with spec 008.

The hashing path runs in a threadpool via :func:`asyncio.to_thread`
so the asyncio event loop stays responsive while the scanner
churns through I/O-bound work.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from romarr.domain.models import Dump, Release
from romarr.identification.hasher import Hasher
from romarr.libraries.scanner.progress import (
    ScanProgressEmitter,
    ScanProgressEvent,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class FullScanResult:
    """Aggregate outcome of a single ``full_scan`` run.

    The orchestrator persists ``last_full_scan_at`` and
    ``last_scan_status`` on the library row and forwards the
    progress events to the WebSocket channel; this dataclass is
    the value the API endpoint returns to the operator.
    """

    library_id: int
    started_at: datetime
    finished_at: datetime
    files_seen: int
    files_processed: int
    files_skipped: int
    files_linked: int
    files_orphaned: int
    files_unmatched: int
    last_status: str = "success"
    last_error: str | None = None
    progress_events: list[ScanProgressEvent] = field(default_factory=list)


_DEFAULT_PROGRESS_EVERY = 100


# ---------------------------------------------------------------------------
# Walk helper (pure — no DB, no hashing)


def walk_library(
    library_path: Path,
    *,
    accepted_extensions: set[str],
) -> Iterator[Path]:
    """Yield every file under ``library_path`` whose suffix is in
    ``accepted_extensions``.

    Directory traversal uses :func:`os.walk`; the iteration order
    matches what :func:`sorted` would produce within each
    directory so progress is reproducible across runs (helps with
    test determinism and operator sanity).

    ``accepted_extensions`` entries are case-insensitive and
    leading-dot tolerant: passing ``{".md", "md", ".MD"}`` all
    match a file named ``foo.MD``.
    """
    normalised = {e.lstrip(".").lower() for e in accepted_extensions}
    for entry in sorted(library_path.rglob("*")):
        if not entry.is_file():
            continue
        ext = entry.suffix.lstrip(".").lower()
        if ext in normalised:
            yield entry


# ---------------------------------------------------------------------------
# Async scanner


async def full_scan(
    *,
    session: AsyncSession,
    library_id: int,
    library_path: Path,
    accepted_extensions: set[str],
    progress_sink: Callable[[ScanProgressEvent], None] | None = None,
    progress_every: int = _DEFAULT_PROGRESS_EVERY,
    hasher: Hasher | None = None,
    create_release_for_unmatched: bool = False,
) -> FullScanResult:
    """Walk ``library_path``; hash and link every matching file.

    Steps:

      1. Walk the directory tree, filtering to files whose suffix
         matches ``accepted_extensions``.
      2. For each file, look up an existing Dump by ``path``. If
         one exists and its ``size_bytes`` matches the on-disk
         size, skip — the file is unchanged (FR-010 idempotent
         re-scan).
      3. Otherwise, hash the file in a threadpool and look up an
         existing Dump by ``sha1``:
           * Same Dump, different path → update ``Dump.path``
             (the file was renamed inside the library).
           * No match → record as ``unmatched`` for the importer
             (spec 008) to handle.
      4. Sweep every Dump whose ``Release.library_id == library_id``
         and whose path no longer exists on disk; mark
         ``Release.status = 'wanted'`` and emit a warning. Orphan
         counts surface in :attr:`FullScanResult.files_orphaned`.
      5. Emit a final :class:`ScanProgressEvent` so the consumer
         sees the terminal counters.

    The function never raises on a single-file failure; per-file
    errors increment the ``unmatched`` counter and surface in the
    progress note.
    """
    if hasher is None:
        hasher = Hasher()

    started_at = datetime.now(UTC)
    progress_events: list[ScanProgressEvent] = []

    def _local_sink(ev: ScanProgressEvent) -> None:
        progress_events.append(ev)
        if progress_sink is not None:
            progress_sink(ev)

    emitter = ScanProgressEmitter(
        library_id=library_id,
        scan_kind="full",
        started_at=started_at,
        sink=_local_sink,
        every=progress_every,
    )

    files_linked = 0

    for file_path in walk_library(library_path, accepted_extensions=accepted_extensions):
        size_on_disk = file_path.stat().st_size
        path_str = str(file_path)
        now = datetime.now(UTC)

        # FR-010: skip if path + size match an existing Dump.
        existing_by_path = (
            await session.execute(select(Dump).where(Dump.path == path_str))
        ).scalar_one_or_none()
        if (
            existing_by_path is not None
            and existing_by_path.size_bytes == size_on_disk
        ):
            emitter.record_skipped(now=now)
            continue

        # Hash off the event loop.
        try:
            hash_result = await asyncio.to_thread(hasher.hash_path, file_path)
        except OSError as exc:
            emitter.record_unmatched(now=datetime.now(UTC))
            progress_events.append(
                emitter.finish(
                    now=datetime.now(UTC),
                    note=f"failed to hash {file_path.name}: {exc}",
                )
            )
            return FullScanResult(
                library_id=library_id,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                files_seen=emitter.files_seen,
                files_processed=emitter.files_processed,
                files_skipped=emitter.files_skipped,
                files_linked=files_linked,
                files_orphaned=emitter.files_orphaned,
                files_unmatched=emitter.files_unmatched,
                last_status="failed",
                last_error=f"OSError on {file_path}: {exc}",
                progress_events=progress_events,
            )

        # Lookup by sha1 — the canonical hash.
        existing_by_hash = (
            await session.execute(select(Dump).where(Dump.sha1 == hash_result.sha1))
        ).scalar_one_or_none()

        if existing_by_hash is not None:
            # Hash match: re-bind to this on-disk path if it has
            # moved. Path is globally unique so an explicit
            # reassignment is safe (the old path location is
            # implicitly retired by the same row's update).
            if existing_by_hash.path != path_str:
                existing_by_hash.path = path_str
                existing_by_hash.size_bytes = size_on_disk
                files_linked += 1
            emitter.record_processed(now=datetime.now(UTC))
            continue

        # No match: leave for spec 008's importer to identify and
        # create the Release. We count it here so the operator
        # sees the number of new files awaiting import.
        emitter.record_unmatched(now=datetime.now(UTC))

        # T040 / FR-014 — when the operator wants the scanner to
        # create Releases (rather than just count), delegate to the
        # importer orchestrator. The MOVE step's in-place fast path
        # detects that the file is already under the library tree
        # and skips the rename, so a successful auto-import lands
        # the Release+Dump on the existing path.
        if create_release_for_unmatched:
            from uuid import uuid4

            from romarr.importer.orchestrator import run_import
            from romarr.importer.types import ImportContext

            try:
                await run_import(
                    ImportContext(
                        source_path=file_path,
                        correlation_id=uuid4(),
                        imported_via="scan",
                    ),
                    session=session,
                )
            except Exception:
                # Per-file failure must not abort the scan; the
                # orchestrator already parks failed identifications
                # in unidentified_dump.
                pass

    await session.flush()

    # FR-011: orphan sweep. Every Dump whose Release belongs to
    # this library and whose on-disk path is gone gets its parent
    # Release transitioned to 'wanted'.
    library_dumps = (
        (
            await session.execute(
                select(Dump)
                .join(Release, Release.id == Dump.release_id)
                .where(Release.library_id == library_id)
            )
        )
        .scalars()
        .all()
    )
    orphaned_release_ids: list[int] = []
    for dump in library_dumps:
        if not Path(dump.path).exists():
            orphaned_release_ids.append(dump.release_id)
            emitter.record_orphan(now=datetime.now(UTC))

    if orphaned_release_ids:
        await session.execute(
            update(Release)
            .where(Release.id.in_(orphaned_release_ids))
            .values(status="wanted", cutoff_met=False)
        )

    finished_at = datetime.now(UTC)
    emitter.finish(now=finished_at, note="full scan complete")
    await session.commit()

    return FullScanResult(
        library_id=library_id,
        started_at=started_at,
        finished_at=finished_at,
        files_seen=emitter.files_seen,
        files_processed=emitter.files_processed,
        files_skipped=emitter.files_skipped,
        files_linked=files_linked,
        files_orphaned=emitter.files_orphaned,
        files_unmatched=emitter.files_unmatched,
        last_status="success",
        last_error=None,
        progress_events=progress_events,
    )


__all__ = ["FullScanResult", "full_scan", "walk_library"]
