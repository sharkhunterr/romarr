"""Importer orchestrator — happy-path driver (spec 008).

Slice 288 ships the *minimal* orchestrator that drives the audit
chain end-to-end for the no-game-match path:

  1. Hash the source file via spec 001's :class:`Hasher`.
  2. Park the file in ``unidentified_dump`` with
     ``rejection_reason='match:no_game'`` so the operator can
     triage it via the manual-match endpoint.
  3. Write a ``success=False`` ``import_history`` row carrying
     the correlation id, started_at / finished_at timestamps,
     and the source SHA-1.
  4. Return an :class:`ImportOutcome` projecting the persisted
     row.

The full happy-path (extract + DAT-match + game-match +
profile-gate + render + move + persist Dump + lifecycle +
notify) lands incrementally in the WATCH / EXTRACT / HASH /
DATMATCH / IDENTIFY / GAMEMATCH / MULTIDISC / PROFILEGATE /
RENDER / MOVE / DBUPDATE / LIFECYCLE / NOTIFY slices listed in
the spec. Today's `run_import` is the single entry-point those
later slices fill in; tests asserting "every input writes an
audit row" can rely on it now.

The watcher loop helpers (``start_watcher`` / ``stop_watcher``)
remain stubs — they land with the WATCH slice when the
``DownloadClient.list_managed_downloads`` helper exists.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from romarr.domain.models import Game, Platform
from romarr.identification.hasher import Hasher
from romarr.identification.parsers import default_dispatcher
from romarr.importer._outcome import make_failure_outcome
from romarr.importer._park import park_in_unidentified
from romarr.importer.errors import ExtractError, GameNotMatched
from romarr.importer.steps.extract import extract as extract_archive

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.importer.types import ImportContext, ImportOutcome


_NOT_IMPLEMENTED_MSG = (
    "{step} not implemented yet — lands with the {phase} slice"
)

_ARCHIVE_SUFFIXES = frozenset({".zip", ".7z", ".rar"})
"""Archive file extensions the orchestrator will run through
EXTRACT before hashing. Mirrors
``romarr.importer.steps.extract._ARCHIVE_SUFFIXES``; consolidated
here so the orchestrator's branching is checkable without
importing the private constant."""


async def run_import(
    context: ImportContext,
    *,
    session: AsyncSession,
    hasher: Hasher | None = None,
) -> ImportOutcome:
    """Run the import pipeline against ``context``.

    Slice 288 ships the audit-only path: hash the file, park it
    as ``match:no_game``, write the failure history row, return
    the projected :class:`ImportOutcome`. Every successful
    failure-path test (``success=False``, ``rejection_reason``
    populated, ``history_id`` non-null) passes against this
    minimum. The full happy-path lands in subsequent slices.

    The caller owns the session — we leave the txn open after
    flushes so callers can compose the import with their own
    work in the same transaction (matches the convention
    established by ``_park.park_in_unidentified`` and
    ``_outcome.persist_failure_history``).
    """
    started_at = datetime.now(UTC)
    monotonic_start = asyncio.get_event_loop().time()

    # Step 1a — EXTRACT (when the source is an archive). On
    # success the working path advances to the extracted ROM;
    # on a parkable ExtractError (bomb / depth-exceeded /
    # bad-archive), the original archive is parked under that
    # rejection reason so the operator's triage UI shows the
    # taxonomy hit (FR-005 / CL004).
    source_path = context.source_path
    extract_failure: ExtractError | None = None
    if (
        source_path.exists()
        and source_path.is_file()
        and source_path.suffix.lower() in _ARCHIVE_SUFFIXES
    ):
        dest_dir = source_path.with_suffix(source_path.suffix + ".extracted")
        try:
            result = await extract_archive(
                archive_path=source_path, dest_dir=dest_dir
            )
            # Pick the first non-archive extracted file as the
            # new working source. Multi-file archives (multi-disc
            # sets) defer to the MULTIDISC slice; for now the
            # single-file shape is enough for the audit chain to
            # exercise the extract path.
            roms = [
                p
                for p in result.extracted_paths
                if p.suffix.lower() not in _ARCHIVE_SUFFIXES
            ]
            if roms:
                source_path = roms[0]
        except ExtractError as exc:
            extract_failure = exc

    # Step 1b — hash the (post-extract) source file. Skip if the
    # path doesn't exist; the failure helper will record a
    # structured reason.
    sha1: str | None = None
    size_bytes = 0

    if (
        extract_failure is None
        and source_path.exists()
        and source_path.is_file()
    ):
        h = hasher or Hasher()
        try:
            hash_result = await asyncio.to_thread(h.hash_path, source_path)
            sha1 = hash_result.sha1
            size_bytes = source_path.stat().st_size
        except OSError:
            # The file disappeared mid-hash; the park + history
            # writes below capture the failure reason.
            sha1 = None

    # Step 2a — IDENTIFY (best-effort): run the filename parser
    # on the source basename so the parked row carries a
    # ``suggested_platform_id`` and ``suggested_game_id`` hint
    # for the operator's manual-match UI. This is audit-grade
    # enrichment only — the full identification cascade
    # (hash-match → header read → DAT verify → game-match) lands
    # with the IDENTIFY / GAMEMATCH slices that follow.
    suggested_platform_id: int | None = None
    suggested_game_id: int | None = None
    if extract_failure is None:
        (
            suggested_platform_id,
            suggested_game_id,
        ) = await _identify_suggestions(session, source_path)

    # Step 2b — park. The rejection reason picks the best signal
    # we have: an extract failure wins (bomb / bad-archive /
    # depth-exceeded — CL004 + CL009), otherwise fall through to
    # ``match:no_game`` until the full game-match path lands.
    rejection_reason = (
        extract_failure.rejection_reason
        if extract_failure is not None
        else "match:no_game"
    )
    park_path = (
        context.source_path if extract_failure is not None else source_path
    )
    try:
        park_size = park_path.stat().st_size if park_path.exists() else 0
    except OSError:
        park_size = 0
    if park_size > 0:
        try:
            await park_in_unidentified(
                session=session,
                source_path=park_path,
                size_bytes=park_size,
                rejection_reason=rejection_reason,
                sha1=sha1,
                library_id=context.library_id,
                suggested_platform_id=suggested_platform_id,
                suggested_game_id=suggested_game_id,
                last_error=(
                    str(extract_failure) if extract_failure is not None else None
                ),
            )
        except Exception:
            # Park failure is non-fatal — the history-row write
            # below still captures the audit trail. The caller
            # decides whether to re-raise.
            pass

    # Step 3 — write the failure history row + project the
    # outcome.
    duration_ms = max(
        0,
        int((asyncio.get_event_loop().time() - monotonic_start) * 1000),
    )
    failure_exc: Exception = (
        extract_failure
        if extract_failure is not None
        else GameNotMatched(
            "no game matched (orchestrator still in audit-only mode)"
        )
    )
    outcome = await make_failure_outcome(
        session=session,
        context=context,
        started_at=started_at,
        exception=failure_exc,
        duration_ms=duration_ms,
        source_hash_sha1=sha1,
    )
    await session.commit()
    return outcome


_IDENTIFY_CONFIDENCE_FLOOR = 0.75
"""Confidence below which the parser's title is considered too
unreliable to use as a Game-match hint. Above the floor + a single
title match in DB → ``suggested_game_id`` is set. Tuned just above
the dispatcher's per-parser threshold (0.7) so a clean
``Title (Region).ext`` clears the bar."""


async def _identify_suggestions(
    session: AsyncSession, source_path: "Path"
) -> tuple[int | None, int | None]:
    """Best-effort IDENTIFY hint for the parked unidentified row.

    Runs the filename dispatcher on ``source_path.name``. When the
    parse exceeds the confidence floor:

      * If ``parsed.platform_slug`` matches a known Platform, sets
        ``suggested_platform_id`` to that platform's id.
      * If exactly one Game (scoped to the suggested platform when
        known, else global) matches the parsed title
        case-insensitively, sets ``suggested_game_id`` to its id.

    Returns ``(suggested_platform_id, suggested_game_id)``. Either
    field may be ``None`` independently. Pure read — no DB writes.
    """
    try:
        parsed = default_dispatcher().parse(source_path.name)
    except Exception:
        return (None, None)

    if not parsed.title or parsed.confidence < _IDENTIFY_CONFIDENCE_FLOOR:
        return (None, None)

    suggested_platform_id: int | None = None
    platform_slug = (
        parsed.extra.get("platform_slug") if parsed.extra else None
    )
    if platform_slug:
        platform = (
            await session.execute(
                select(Platform.id).where(Platform.slug == platform_slug)
            )
        ).scalar_one_or_none()
        if platform is not None:
            suggested_platform_id = int(platform)

    title_query = select(Game.id).where(
        func.lower(Game.title) == parsed.title.lower()
    )
    if suggested_platform_id is not None:
        title_query = title_query.where(
            Game.platform_id == suggested_platform_id
        )
    matches = (await session.execute(title_query.limit(2))).scalars().all()

    suggested_game_id: int | None = None
    if len(matches) == 1:
        suggested_game_id = int(matches[0])

    return (suggested_platform_id, suggested_game_id)


_watcher: "WatcherLoop | None" = None


async def start_watcher(
    *,
    get_clients: "ClientProvider",
    dispatcher: "Dispatcher",
    interval_seconds: float | None = None,
) -> "WatcherLoop":
    """Spawn the polling watcher background task (FR-001).

    Wired into the application lifespan. The watcher polls every
    configured download client every ``interval_seconds`` (default
    30 s) for completed downloads and hands new ones to the
    dispatcher (typically a wrapper around :func:`run_import`).
    """
    from romarr.importer.steps.watch import (
        DEFAULT_INTERVAL_SECONDS,
        WatcherLoop,
    )

    global _watcher
    if _watcher is not None and _watcher.running:
        return _watcher

    _watcher = WatcherLoop(
        get_clients=get_clients,
        dispatcher=dispatcher,
        interval_seconds=(
            interval_seconds
            if interval_seconds is not None
            else DEFAULT_INTERVAL_SECONDS
        ),
    )
    await _watcher.start()
    return _watcher


async def stop_watcher() -> None:
    """Cancel the polling watcher background task on shutdown."""
    global _watcher
    if _watcher is None:
        return
    await _watcher.stop()
    _watcher = None


if TYPE_CHECKING:
    from romarr.importer.steps.watch import (
        ClientProvider,
        Dispatcher,
        WatcherLoop,
    )


__all__ = ["run_import", "start_watcher", "stop_watcher"]
