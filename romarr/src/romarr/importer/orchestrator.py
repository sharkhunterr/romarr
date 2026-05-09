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

from romarr.domain.models import Game, Platform, Release
from romarr.identification.dat.manager import DatManager
from romarr.identification.hasher import Hasher
from romarr.identification.headers import (
    HeaderReadStatus,
    InesReader,
    Iso9660Reader,
    MegaDriveReader,
)
from romarr.identification.headers.base import (
    BaseHeaderReader,
    UnsupportedPlatformError,
)
from romarr.identification.parsers import default_dispatcher
from romarr.importer._outcome import make_failure_outcome
from romarr.importer._park import park_in_unidentified
from romarr.importer.errors import ExtractError, GameNotMatched
from romarr.importer.steps.extract import extract as extract_archive
from romarr.importer.steps.game_match import match_to_game

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.importer.types import ImportContext, ImportOutcome
    from romarr.notifications.channel import EventChannel


_NOT_IMPLEMENTED_MSG = (
    "{step} not implemented yet — lands with the {phase} slice"
)

_ARCHIVE_SUFFIXES = frozenset({".zip", ".7z", ".rar"})
"""Archive file extensions the orchestrator will run through
EXTRACT before hashing. Mirrors
``romarr.importer.steps.extract._ARCHIVE_SUFFIXES``; consolidated
here so the orchestrator's branching is checkable without
importing the private constant."""

_FORMAT_FAMILY_BY_SUFFIX: dict[str, str] = {
    ".zip": "zip",
    ".7z": "7z",
    ".rar": "rar",
    ".chd": "chd",
    ".rvz": "rvz",
    ".nkit": "nkit",
    ".cso": "cso",
    ".pbp": "pbp",
}
"""File-suffix → format-family map for the Quality profile's
``allowed_formats`` check. Extensions not in this map are
classified as ``raw`` (.md / .nes / .sfc / .smc / .gb / .gba /
.iso / .bin / etc — the canonical uncompressed dumps)."""


def _classify_file_format(path: "Path") -> str:
    """Map ``path.suffix`` to a format family string the spec 006
    Quality profile evaluates against ``allowed_formats``.

    Unknown extensions fall through to ``raw`` so the typical
    raw-rom case clears the gate without an explicit
    suffix-by-suffix allow-list.
    """
    return _FORMAT_FAMILY_BY_SUFFIX.get(path.suffix.lower(), "raw")


_BLOCKLIST_WORTHY_REASONS = frozenset(
    {
        "extract:bomb-detected",
        "extract:bad-archive",
        "extract:depth-exceeded",
        "destination_collision",
        "move:copy_hash_mismatch",
    }
)
"""Content-correctness rejection reasons that auto-blocklist
the source release per CL001 / FR-035 / SC-006. Transient
sub-reasons (hash:failed, move:permission_error,
move:disk_full, lock:timeout, profile:*, routing:*) DO NOT
blocklist — they're operator-config or environmental and a
re-grab might succeed."""


async def run_import(
    context: ImportContext,
    *,
    session: AsyncSession,
    hasher: Hasher | None = None,
    event_channel: "EventChannel | None" = None,
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
    hash_result = None

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
            hash_result = None

    # Step 2a — IDENTIFY (Header → Parser → DAT → GAMEMATCH).
    # Returns three signals: the suggested_platform_id +
    # suggested_game_id (always populated when known — feeds the
    # park hint), and monitored_game_id (only set when GAMEMATCH
    # resolves to a confident monitored hit — feeds the auto-
    # import gate at Step 2b).
    suggested_platform_id: int | None = None
    suggested_game_id: int | None = None
    monitored_game_id: int | None = None
    if extract_failure is None:
        (
            suggested_platform_id,
            suggested_game_id,
            monitored_game_id,
        ) = await _identify_suggestions(session, source_path, sha1=sha1)

    # Slice 369: when the dispatcher carried a pre-resolved game
    # id from the parent ``queue_entry`` (manual-grab path),
    # trust it and override the filename-fuzzy result. The
    # operator already told us which game this download is for;
    # re-running the fuzzy step against torrent names like
    # ``Harry Potter and the Goblet of Fire _axekin.com_`` would
    # just lose the answer because the foundation parser can't
    # recover the canonical title.
    if context.pre_matched_game_id is not None:
        suggested_game_id = context.pre_matched_game_id
        monitored_game_id = context.pre_matched_game_id
        if suggested_platform_id is None:
            from romarr.domain.models import Game as _Game

            row = (
                await session.execute(
                    select(_Game.platform_id).where(
                        _Game.id == context.pre_matched_game_id
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                suggested_platform_id = int(row)

    # Step 2b — AUTO-IMPORT: when GAMEMATCH resolved to a
    # monitored Game AND that Game has exactly one wanted
    # Release, we have enough confidence to bypass parking and
    # run an in-place import. Mirrors the manual-match endpoint's
    # contract through ``manual_import_known``.
    if (
        extract_failure is None
        and monitored_game_id is not None
        and hash_result is not None
        and source_path.exists()
        and source_path.is_file()
    ):
        # Pick the auto-import target Release. Prefer wanted (the
        # first-import case); allow imported so re-runs against
        # the same file coalesce idempotently (FR-033). Multi-
        # Release ambiguity falls through to parking unless the
        # parser-derived regions disambiguate to exactly one.
        candidate_rows = (
            await session.execute(
                select(Release.id, Release.regions)
                .where(
                    Release.game_id == monitored_game_id,
                    Release.status.in_(("wanted", "imported")),
                )
                .order_by(Release.id)
            )
        ).all()
        candidates: list[int] = [int(r[0]) for r in candidate_rows]

        # T040 / FR-014 — scanner-driven import: when the Game has no
        # wanted/imported Release yet but the filename has parseable
        # region/dump info, create a fresh wanted Release so the
        # auto-import has a binding target. Originally limited to
        # the scan path; slice 373 also opens this to manual-grab
        # downloads (``pre_matched_game_id`` set) — the operator
        # already chose the game, so creating the matching Release
        # is what they actually want.
        if not candidates and (
            context.imported_via == "scan"
            or context.pre_matched_game_id is not None
        ):
            try:
                parsed_for_create = default_dispatcher().parse(source_path.name)
            except Exception:
                parsed_for_create = None
            if parsed_for_create is not None:
                from romarr.domain.enums import (
                    DumpStatus as _DumpStatus,
                    NamingConvention as _NamingConvention,
                )

                regions_for_release = (
                    list(parsed_for_create.regions)
                    if parsed_for_create.regions
                    else []
                )
                languages_for_release = (
                    list(parsed_for_create.languages)
                    if parsed_for_create.languages
                    else []
                )
                # Pick library binding from the matched Game's
                # platform — when a Library covers this platform,
                # bind to the first one. Falls back to the Release's
                # parent Game's existing library hint when present.
                library_id_for_release: int | None = None
                from romarr.libraries.models import Library as _LibModel

                lib_rows = (
                    await session.execute(
                        select(_LibModel.id).order_by(_LibModel.id)
                    )
                ).scalars().all()
                library_id_for_release = (
                    int(lib_rows[0]) if lib_rows else None
                )

                new_release = Release(
                    game_id=monitored_game_id,
                    name=source_path.stem,
                    regions=regions_for_release,
                    languages=languages_for_release,
                    dump_status=_DumpStatus.VERIFIED,
                    naming_convention=_NamingConvention.NO_INTRO,
                    status="wanted",
                    library_id=library_id_for_release,
                )
                session.add(new_release)
                await session.commit()
                await session.refresh(new_release)
                candidates = [new_release.id]
                candidate_rows = [(new_release.id, regions_for_release)]

        if len(candidates) > 1:
            # Region-disambiguate: parse the filename for region
            # tags and pick the Release whose regions tuple
            # overlaps. Single-overlap → that's the target;
            # zero or multi-overlap → fall through to parking.
            try:
                parsed = default_dispatcher().parse(source_path.name)
                parsed_regions = (
                    set(parsed.regions) if parsed.regions else set()
                )
            except Exception:
                parsed_regions = set()
            if parsed_regions:
                overlapping = [
                    int(rid)
                    for rid, regions in candidate_rows
                    if regions and (set(regions) & parsed_regions)
                ]
                if len(overlapping) == 1:
                    candidates = overlapping

        if len(candidates) == 1:
            from sqlalchemy.exc import IntegrityError
            from romarr.importer._idempotency import find_existing_dump
            from romarr.importer._manual import manual_import_known
            from romarr.importer._outcome import make_success_outcome

            release_id = int(candidates[0])
            file_format = _classify_file_format(source_path)
            from romarr.importer.errors import MoveError

            # MOVE step (FR-007 / CL003) — when the picked Release
            # is bound to a Library whose path exists on disk, move
            # the source file into the library tree before the DB
            # update. Hardlink-first per FR-015 of spec 009; cross-
            # fs falls back to copy+verify. Destination-collision
            # (different SHA-1 already at dest, no force) → park
            # with ``destination_collision`` rejection reason
            # (CL003).
            move_dest: "Path | None" = None
            destination_collision_failure: MoveError | None = None
            try:
                move_dest = await _maybe_move_to_library(
                    session=session,
                    release_id=release_id,
                    source_path=source_path,
                    sha1=sha1,
                    force=context.force,
                )
            except MoveError as exc:
                if exc.rejection_reason == "destination_collision":
                    destination_collision_failure = exc
                    move_dest = None
                else:
                    move_dest = None  # other move errors → in-place
            if destination_collision_failure is not None:
                # CL003 — park with destination_collision; auto-
                # blocklist fires from the failure-handling block
                # below since this rejection is in
                # _BLOCKLIST_WORTHY_REASONS.
                try:
                    await park_in_unidentified(
                        session=session,
                        source_path=context.source_path,
                        size_bytes=size_bytes,
                        rejection_reason="destination_collision",
                        sha1=sha1,
                        library_id=context.library_id,
                        suggested_platform_id=suggested_platform_id,
                        suggested_game_id=monitored_game_id,
                        last_error=str(destination_collision_failure),
                    )
                except Exception:
                    pass
                duration_ms = max(
                    0,
                    int(
                        (
                            asyncio.get_event_loop().time()
                            - monotonic_start
                        )
                        * 1000
                    ),
                )
                failure_outcome = await make_failure_outcome(
                    session=session,
                    context=context,
                    started_at=started_at,
                    exception=destination_collision_failure,
                    duration_ms=duration_ms,
                    source_hash_sha1=sha1,
                )
                # Auto-blocklist on destination collision.
                try:
                    await _auto_blocklist(
                        session=session,
                        release_title=context.source_path.name,
                        reason="destination_collision",
                        hash_sha1=sha1,
                    )
                except Exception:
                    pass
                await session.commit()
                return failure_outcome
            dest_path = move_dest if move_dest is not None else source_path

            # T084 / FR-021 / US4.2 — PROFILE-GATE. When the
            # picked Release is bound to a Library, evaluate the
            # 4 profile gates (quality / region / dump /
            # language). REJECT → fall through to parking
            # (failure path); REJECT + context.force=True →
            # pass with a warning on the outcome.
            gate_result = await _evaluate_profile_gate(
                session=session,
                release_id=release_id,
                source_path=source_path,
                file_format=file_format,
                hash_result=hash_result,
                force=context.force,
            )
            if gate_result is not None and not gate_result.passed:
                # Hard reject → record the audit failure and
                # park with the structured rejection reason.
                rejection_reason = (
                    gate_result.rejection_reason.value
                    if gate_result.rejection_reason is not None
                    else "profile:reject"
                )
                try:
                    await park_in_unidentified(
                        session=session,
                        source_path=source_path,
                        size_bytes=size_bytes,
                        rejection_reason=rejection_reason,
                        sha1=sha1,
                        library_id=context.library_id,
                        suggested_platform_id=suggested_platform_id,
                        suggested_game_id=monitored_game_id,
                        last_error=(
                            f"profile_gate {gate_result.failing_gate} "
                            f"rejected"
                        ),
                    )
                except Exception:
                    pass
                duration_ms = max(
                    0,
                    int(
                        (
                            asyncio.get_event_loop().time()
                            - monotonic_start
                        )
                        * 1000
                    ),
                )
                failure_outcome = await make_failure_outcome(
                    session=session,
                    context=context,
                    started_at=started_at,
                    exception=GameNotMatched(
                        f"profile_gate {gate_result.failing_gate} "
                        "rejected"
                    ),
                    duration_ms=duration_ms,
                    source_hash_sha1=sha1,
                )
                await session.commit()
                return failure_outcome
            outcome = None
            try:
                outcome = await manual_import_known(
                    session=session,
                    context=context,
                    release_id=release_id,
                    game_id=monitored_game_id,
                    dest_path=dest_path,
                    file_format=file_format,
                    original_filename=source_path.name,
                    hashes=hash_result,
                )
                await session.commit()
            except IntegrityError:
                # Concurrent-import race (FR-033 / SC-007). Another
                # coroutine inserted the Dump between our
                # find_existing_dump check and our flush. Roll back,
                # re-query, project a coalesced success outcome.
                await session.rollback()
                existing = await find_existing_dump(
                    session=session,
                    sha1=hash_result.sha1,
                    release_id=release_id,
                )
                if existing is not None:
                    outcome = await make_success_outcome(
                        session=session,
                        context=context,
                        started_at=started_at,
                        duration_ms=max(
                            0,
                            int(
                                (
                                    asyncio.get_event_loop().time()
                                    - monotonic_start
                                )
                                * 1000
                            ),
                        ),
                        dest_path=existing.path,
                        game_id=monitored_game_id,
                        release_id=release_id,
                        dump_id=existing.id,
                        source_hash_sha1=hash_result.sha1,
                        confidence=1.0,
                        coalesced=True,
                        warning=None,
                    )
                    await session.commit()
            except Exception:
                # Other failure (fs / DB / integrity-but-no-existing-
                # row) → fall through to parking. The audit row
                # written by the park branch carries the operator-
                # actionable failure surface.
                outcome = None
            if outcome is not None:
                # NOTIFY: emit OnImport so the spec 011 dispatcher
                # fans out. Best-effort — a publish failure must
                # not invalidate the committed import.
                if event_channel is not None:
                    try:
                        await _emit_on_import(
                            event_channel=event_channel,
                            session=session,
                            game_id=monitored_game_id,
                            release_id=release_id,
                            outcome=outcome,
                            hash_result=hash_result,
                        )
                    except Exception:
                        pass
                # LIFECYCLE: tag the originating download with the
                # ``romarr-imported`` tag (FR-013). Best-effort —
                # failure must not invalidate the committed import.
                if (
                    context.download_client_id is not None
                    and context.download_client_native_id is not None
                ):
                    try:
                        await _tag_downloaded_imported(
                            session=session,
                            client_id=context.download_client_id,
                            native_id=context.download_client_native_id,
                        )
                    except Exception:
                        pass
                # EXPORTER fan-out (T059 / spec 009 EXP-ESDE).
                # Re-emit ``gamelist.xml`` when the owning
                # Library's ``exporter_esde_enabled`` flag is
                # True; skip when False (no file written) per
                # FR-018. Best-effort — emission failure must
                # not invalidate the committed import.
                try:
                    await _dispatch_esde_exporter(
                        session=session,
                        release_id=release_id,
                        dump_path=dest_path,
                    )
                except Exception:
                    pass
                # LIFECYCLE: preserve_archive (FR-005 / T030). When
                # the original source was an archive AND the
                # owning Library's preserve_archive flag is False,
                # delete the archive after a successful in-place
                # import. Best-effort — failure here must not
                # invalidate the committed import.
                if (
                    context.source_path != source_path
                    and context.source_path.suffix.lower()
                    in _ARCHIVE_SUFFIXES
                ):
                    try:
                        await _maybe_delete_archive(
                            session=session,
                            release_id=release_id,
                            archive_path=context.source_path,
                        )
                    except Exception:
                        pass
                return outcome

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

    # CL001 / T083 / FR-035 / SC-006 — subreason-aware auto-
    # blocklist. When the failure rejection_reason is one of
    # the content-correctness reasons (bomb / bad-archive /
    # depth-exceeded / destination_collision /
    # move_hash_mismatch), add a Blocklist row with
    # ``added_by='system'`` so the search engine doesn't re-
    # grab the same bad release. Best-effort — a blocklist
    # failure can't invalidate the audit row.
    if rejection_reason in _BLOCKLIST_WORTHY_REASONS:
        try:
            await _auto_blocklist(
                session=session,
                release_title=context.source_path.name,
                reason=rejection_reason,
                hash_sha1=sha1,
            )
        except Exception:
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


async def _dispatch_esde_exporter(
    *,
    session: AsyncSession,
    release_id: int,
    dump_path: "Path",
) -> None:
    """T059 / FR-018 — re-render the per-platform
    ``gamelist.xml`` after a successful import iff the owning
    Library's ``exporter_esde_enabled`` flag is True. No-op
    when disabled.

    The renderer needs a streaming view of every Game in the
    (library, platform) tuple — for the v1 slice we render a
    single-Game gamelist as a structural marker so the gate
    contract is exercised. The full
    "materialize-every-Game-on-platform" rendering ships with
    the per-import fan-out slice that integrates the spec 002
    metadata aggregator.

    Best-effort: caller wraps in try/except so an emission
    failure (permission, disk full) can't invalidate the
    committed import.
    """
    from pathlib import Path as _Path

    from romarr.libraries.exporters.esde import (
        EsdeGame,
        render_gamelist_xml,
        write_gamelist_atomic,
    )
    from romarr.libraries.models import Library

    release = await session.get(Release, release_id)
    if release is None or release.library_id is None:
        return

    library = await session.get(Library, release.library_id)
    if library is None or not library.exporter_esde_enabled:
        return  # T059 — disabled flag → no-op

    game = await session.get(Game, release.game_id)
    if game is None:
        return

    platform_slug_row = (
        await session.execute(
            select(Platform.slug).where(Platform.id == game.platform_id)
        )
    ).scalar_one_or_none()
    if not platform_slug_row:
        return

    target_dir = _Path(library.path) / platform_slug_row
    if not target_dir.exists():
        return

    # Compute the rom_path relative to the gamelist.xml's
    # directory (the per-platform subfolder).
    try:
        rom_relative = dump_path.relative_to(target_dir)
    except ValueError:
        rom_relative = _Path(dump_path.name)

    esde_game = EsdeGame(
        slug=game.slug,
        title=game.title,
        rom_path=f"./{rom_relative}",
    )
    xml_bytes = render_gamelist_xml([esde_game])
    written = write_gamelist_atomic(target_dir, xml_bytes)

    # T077 / FR-019 — record the emission so the operator UI can
    # surface "last gamelist.xml emit" per library + exporter.
    try:
        from romarr.libraries.exporters._runs import record_exporter_run

        await record_exporter_run(
            session=session,
            library_id=library.id,
            exporter_name="esde",
            status="ok" if written else "coalesced",
        )
    except Exception:
        pass


async def _maybe_move_to_library(
    *,
    session: AsyncSession,
    release_id: int,
    source_path: "Path",
    sha1: str | None,
    force: bool,
) -> "Path | None":
    """FR-007 / CL003 — move ``source_path`` into the owning
    Library's tree. Returns the new dest path, or None when
    the move couldn't be performed and the caller should
    keep the in-place ``source_path``.

    Skip cases (return None):
      * Release has no library binding;
      * Library row missing;
      * Library.path doesn't exist on disk (test-fixture / pre-
        deployment scenario — the Dump stays in-place rather
        than failing);
      * Source path doesn't exist;
      * No SHA-1 (can't verify post-move).

    Raises ``MoveError`` on destination collision or other
    move-step failures the caller routes to the structured
    rejection_reason taxonomy.

    Destination layout: ``<library.path>/<platform.slug>/<source_filename>``.
    The naming-template-driven RENDER step (FR-008) lands
    later — this is the simple structural placement.
    """
    from pathlib import Path as _Path

    from romarr.importer.steps.move import move_atomic
    from romarr.libraries.models import Library

    if sha1 is None or not source_path.exists():
        return None

    release = await session.get(Release, release_id)
    if release is None or release.library_id is None:
        return None

    library = await session.get(Library, release.library_id)
    if library is None:
        return None

    library_path = _Path(library.path)
    if not library_path.exists():
        # Test fixture / pre-deployment — keep the file in-place.
        return None

    # Resolve platform via Game.platform_id (avoid the
    # ORM relationship which would trigger lazy load on the
    # session's connection — async-incompatible).
    platform_slug_row = (
        await session.execute(
            select(Platform.slug)
            .join(Game, Game.platform_id == Platform.id)
            .where(Game.id == release.game_id)
        )
    ).scalar_one_or_none()
    platform_slug = platform_slug_row or "unknown"

    dest_path = library_path / platform_slug / source_path.name
    # In-place fast path: source already lives at the destination.
    # The scanner-driven import case (`imported_via="scan"`) hits
    # this — the file is already under the library tree, so the
    # MOVE step is a no-op and we hand back the existing path.
    try:
        if source_path.resolve() == dest_path.resolve():
            return dest_path
    except OSError:
        pass

    result = await move_atomic(
        source=source_path,
        dest=dest_path,
        expected_sha1=sha1,
        force=force,
    )
    return result.dest


async def _evaluate_profile_gate(
    *,
    session: AsyncSession,
    release_id: int,
    source_path: "Path",
    file_format: str,
    hash_result,  # type: ignore[no-untyped-def]
    force: bool,
):  # type: ignore[no-untyped-def]
    """T084 / FR-021 — evaluate the 4 profile gates against the
    candidate Release.

    Returns ``None`` when the Release has no Library binding
    (skip the gate, legacy path); otherwise a
    :class:`ProfileGateResult`. Caller acts on
    ``passed`` / ``rejection_reason`` / ``warning``.
    """
    from romarr.importer.steps.profile_gate import apply_profile_gate
    from romarr.libraries.models import Library
    from romarr.profiles.models import (
        DumpProfile,
        LanguageProfile,
        QualityProfile,
        RegionProfile,
    )
    from romarr.profiles.types import ReleaseFacts

    release = await session.get(Release, release_id)
    if release is None or release.library_id is None:
        return None  # legacy path — no profile gate

    library = await session.get(Library, release.library_id)
    if library is None:
        return None

    quality = await session.get(
        QualityProfile, library.quality_profile_id
    )
    region = await session.get(RegionProfile, library.region_profile_id)
    dump = await session.get(DumpProfile, library.dump_profile_id)
    language = await session.get(
        LanguageProfile, library.language_profile_id
    )
    if any(p is None for p in (quality, region, dump, language)):
        return None  # profile data incomplete — skip gate

    facts = ReleaseFacts(
        title=release.name,
        regions=tuple(release.regions or ()),
        languages=tuple(release.languages or ()),
        revision=release.revision,
        dump_status=release.dump_status,
        naming_convention=release.naming_convention,
        file_format=file_format,
        release_size=hash_result.size_bytes if hash_result else None,
    )

    return apply_profile_gate(
        quality=quality,
        region=region,
        dump=dump,
        language=language,
        facts=facts,
        force=force,
    )


async def _auto_blocklist(
    *,
    session: AsyncSession,
    release_title: str,
    reason: str,
    hash_sha1: str | None,
) -> None:
    """CL001 / T083 — auto-blocklist on content-correctness
    failure. Adds a row to the spec 007 blocklist with
    ``added_by='system'`` so the search engine doesn't re-grab
    the same bad release on the next RSS pass.

    Best-effort: caller wraps in try/except so a blocklist
    failure (DB constraint, missing-match-field) can't
    invalidate the audit row.

    The Blocklist's at-least-one-match-field invariant is
    documented at the Pydantic schema layer; the underlying
    DB columns are all nullable, so an "audit-only" entry
    (release_title + reason, no hash) lands cleanly. Future
    grabs match by hash when available; without a hash the
    entry serves as a record of what failed for the
    operator's "Blocklisted Releases" UI.
    """
    from romarr.search.blocklist import add_entry

    await add_entry(
        session=session,
        release_title=release_title,
        reason=reason,
        hash_sha1=hash_sha1,
        added_by="system",
    )


async def _maybe_delete_archive(
    *,
    session: AsyncSession,
    release_id: int,
    archive_path: "Path",
) -> None:
    """FR-005 / T030 — delete the archive after a successful
    in-place import iff the owning Library's
    ``preserve_archive`` flag is False.

    Resolves the Library by walking
    ``Release.library_id``; when the Release isn't bound to a
    Library (legacy data, missing FK), the archive is preserved
    by default — the operator's intent isn't known.

    Best-effort: the caller wraps in try/except so an unlink
    failure (filesystem permission, file already gone) can't
    invalidate the committed import.
    """
    from romarr.libraries.models import Library

    release = await session.get(Release, release_id)
    if release is None or release.library_id is None:
        return
    library = await session.get(Library, release.library_id)
    if library is None:
        return
    if library.preserve_archive:
        return  # operator opted to keep archives

    if archive_path.exists() and archive_path.is_file():
        try:
            archive_path.unlink()
        except OSError:
            return


async def _tag_downloaded_imported(
    *,
    session: AsyncSession,
    client_id: int,
    native_id: str,
) -> None:
    """Tag the originating download with ``romarr-imported``
    (FR-013). Best-effort: caller wraps in try/except so a
    client error can't invalidate the committed import.

    Loads the :class:`DownloadClient` row via the spec 005
    factory, instantiates the matching impl, and calls
    ``set_imported_tag``. Stub clients (Transmission /
    Deluge / NZBGet) raise NotImplementedError; SAB's
    implementation is a no-op (SAB has no per-job tag
    surface).
    """
    from romarr.downloaders.factory import build_client_from_row
    from romarr.downloaders.models import (
        DownloadClient as DownloadClientRow,
    )

    row = await session.get(DownloadClientRow, client_id)
    if row is None:
        return
    impl = build_client_from_row(row)
    await impl.set_imported_tag(native_id)


async def _emit_on_import(
    *,
    event_channel: "EventChannel",
    session: AsyncSession,
    game_id: int,
    release_id: int,
    outcome: "ImportOutcome",
    hash_result,  # type: ignore[no-untyped-def]
) -> None:
    """Publish an OnImport notification event after a successful
    auto-import. Loads the Game + Release from session so the
    payload's GameRef / ReleaseRef are fully populated.

    Best-effort: caller wraps this in try/except so a publish
    failure can't invalidate the committed import.
    """
    from romarr.notifications.types import (
        DumpRef,
        EventType,
        GameRef,
        OnImportPayload,
        ReleaseRef,
    )

    game_row = await session.get(Game, game_id)
    release_row = await session.get(Release, release_id)
    if game_row is None or release_row is None:
        return  # row vanished — defensive

    platform_row = await session.get(Platform, game_row.platform_id)
    platform_slug = platform_row.slug if platform_row else ""
    platform_name = platform_row.name if platform_row else ""

    region = (
        release_row.regions[0]
        if release_row.regions
        else None
    )

    payload = OnImportPayload(
        event_type=EventType.ON_IMPORT,
        game=GameRef(
            id=game_row.id,
            title=game_row.title,
            platform_slug=platform_slug,
            platform_name=platform_name,
        ),
        release=ReleaseRef(
            id=release_row.id,
            name=release_row.name,
            region=region,
            languages=tuple(release_row.languages or ()),
            revision=release_row.revision,
            dump_status=str(release_row.dump_status),
            naming_convention=str(release_row.naming_convention),
        ),
        dump=DumpRef(
            path=str(outcome.dest_path) if outcome.dest_path else "",
            sha1=hash_result.sha1,
            crc32=hash_result.crc32 or None,
            md5=hash_result.md5 or None,
            size_bytes=hash_result.size_bytes,
        ),
    )
    await event_channel.publish(payload)


_IDENTIFY_CONFIDENCE_FLOOR = 0.75
"""Confidence below which the parser's title is considered too
unreliable to use as a Game-match hint. Above the floor + a single
title match in DB → ``suggested_game_id`` is set. Tuned just above
the dispatcher's per-parser threshold (0.7) so a clean
``Title (Region).ext`` clears the bar."""


_HEADER_READERS: tuple[BaseHeaderReader, ...] = (
    InesReader(),
    MegaDriveReader(),
    Iso9660Reader(),
)
"""Header readers tried in order during IDENTIFY enrichment. The
ISO9660 reader's internal cascade also disambiguates PSX/PS2/Xbox/
Saturn/Dreamcast/MegaCD by inspecting volume contents (CL002 of
spec 001). Stub readers (3DS, NDS, etc.) raise
:class:`UnsupportedPlatformError` and are silently skipped."""


def _read_header_platform(source_path: "Path") -> str | None:
    """Try each header reader; return the first OK platform_slug.

    Stub readers (3DS / NDS / PSP / Vita / Switch / Wii / GC / GBA)
    raise :class:`UnsupportedPlatformError`; we silently skip them
    so a partial reader set doesn't block the rest of the cascade.
    """
    for reader in _HEADER_READERS:
        try:
            result = reader.read(source_path)
        except UnsupportedPlatformError:
            continue
        except OSError:
            continue
        if result.status is HeaderReadStatus.OK and result.platform_slug:
            return result.platform_slug
    return None


async def _identify_suggestions(
    session: AsyncSession,
    source_path: "Path",
    *,
    sha1: str | None = None,
) -> tuple[int | None, int | None, int | None]:
    """Best-effort IDENTIFY hint for the parked unidentified row.

    Runs two parallel cascades whose hints feed the parking step:

      1. **Header read**: try each registered header reader in
         order; the first that returns ``OK`` with a
         ``platform_slug`` wins. Header reads work even when the
         filename is uninformative (e.g., ``rom.bin``); when
         the file's leading bytes encode a recognizable signature
         (iNES magic, ``SEGA MEGA DRIVE``, ISO9660 PVD), this is
         a high-confidence platform signal.

      2. **Filename parse**: dispatcher cascade across No-Intro /
         Redump / TOSEC / GoodTools / Scene. When parser confidence
         exceeds the floor + the title resolves to exactly one
         Game in the catalogue, we suggest that Game's id.

    Header-derived ``platform_slug`` takes precedence over the
    parser's. Pure read — no DB writes.
    """
    suggested_platform_id: int | None = None

    # Header read first — runs blocking I/O, so threadpool it. Don't
    # let a stat / mmap failure cascade out: catching at the call
    # site keeps the orchestrator's audit chain robust.
    try:
        header_platform_slug = await asyncio.to_thread(
            _read_header_platform, source_path
        )
    except Exception:
        header_platform_slug = None

    if header_platform_slug:
        platform = (
            await session.execute(
                select(Platform.id).where(Platform.slug == header_platform_slug)
            )
        ).scalar_one_or_none()
        if platform is not None:
            suggested_platform_id = int(platform)

    # Filename parser
    try:
        parsed = default_dispatcher().parse(source_path.name)
    except Exception:
        parsed = None

    if (
        parsed is not None
        and parsed.title
        and parsed.confidence >= _IDENTIFY_CONFIDENCE_FLOOR
        and suggested_platform_id is None
    ):
        # Parser-suggested platform only fires when the header
        # reader didn't already pin one (header signal is more
        # authoritative — actual bytes vs. a filename guess).
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

    # DAT-match: when we have a SHA-1 + platform_id, query the
    # local DAT cache. A high-authority DAT match (No-Intro >
    # Redump > TOSEC, CL001 of spec 001) often carries a
    # canonical Game name we can feed into game-match.
    dat_name: str | None = None
    if sha1 is not None and suggested_platform_id is not None:
        try:
            dat_manager = DatManager(session)
            best = await dat_manager.best_match_by_sha1(
                platform_id=suggested_platform_id, sha1=sha1
            )
        except Exception:
            best = None
        if best is not None and best.winner.name:
            dat_name = best.winner.name

    # Game-match: feed every title we know about (parsed
    # filename + DAT canonical name) to the spec 008 fuzzy
    # matcher. Returns the best monitored hit (game_id) or
    # the best unmonitored suggestion (suggested_game_id);
    # either populates the parked row's ``suggested_game_id``
    # so the operator's manual-match UI can one-click confirm.
    suggested_game_id: int | None = None
    monitored_game_id: int | None = None
    titles: list[str] = []
    if (
        parsed is not None
        and parsed.title
        and parsed.confidence >= _IDENTIFY_CONFIDENCE_FLOOR
    ):
        titles.append(parsed.title)
    if dat_name:
        titles.append(dat_name)

    if titles and suggested_platform_id is not None:
        try:
            gm_result = await match_to_game(
                session=session,
                platform_id=suggested_platform_id,
                titles=titles,
            )
        except Exception:
            gm_result = None
        if gm_result is not None:
            suggested_game_id = (
                gm_result.game_id or gm_result.suggested_game_id
            )
            # ``game_id`` is non-None only when the match was a
            # confident hit against a *monitored* Game (signal in
            # ``title_exact`` or ``title_fuzzy`` ≥ 90). That's the
            # green light for an in-place auto-import — caller
            # gates the success path on this field.
            monitored_game_id = gm_result.game_id
    elif titles:
        # No platform pinned — fall back to a single global
        # case-insensitive title lookup. Picks at most one Game;
        # ambiguous matches stay None (operator triages).
        for title in titles:
            global_query = select(Game.id).where(
                func.lower(Game.title) == title.lower()
            )
            global_matches = (
                await session.execute(global_query.limit(2))
            ).scalars().all()
            if len(global_matches) == 1:
                suggested_game_id = int(global_matches[0])
                break

    return (suggested_platform_id, suggested_game_id, monitored_game_id)


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
