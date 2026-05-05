"""Manual-import flow (spec 009 — Phase 12 MANUAL).

The operator's manual-import surface lets them pick exactly which
files to bring into the library. Two pure-async entry points
mirror the API surface:

  * :func:`list_candidates` — walk a folder + run the IDENTIFY
    enrichment over each accepted file. Pure read; no DB writes
    (FR-022 — listing must not mutate state). Returns enough
    metadata for the operator UI to show suggestions per file.

  * :func:`bulk_import` — accepts a list of operator decisions
    (one per file: import / skip / override Game) and delegates
    each to the spec 008 importer. Per-entry errors are isolated
    so one failure doesn't drop the whole batch (FR-024 — routing
    check fires per entry, not per batch).

Both entry points respect the configured ``accepted_extensions``
set so a folder full of ``.txt`` notes doesn't surface as
candidates.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from sqlalchemy import func, select

from romarr.domain.models import Game, Platform
from romarr.identification.parsers import default_dispatcher
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_LISTING_CONFIDENCE_FLOOR = 0.75
"""Match the orchestrator's IDENTIFY enrichment threshold so the
manual-listing UI shows the same Game suggestion the orchestrator
would persist on a hands-off import."""


@dataclass(frozen=True, slots=True)
class ManualImportListing:
    """One row in the operator's manual-import grid.

    Pure value object — no ORM, no DB. Everything below
    ``path`` / ``size_bytes`` is *suggestion* (the operator can
    override before the bulk POST).
    """

    path: Path
    size_bytes: int
    parsed_title: str | None = None
    parsed_convention: str | None = None
    parsed_regions: tuple[str, ...] = ()
    parsed_languages: tuple[str, ...] = ()
    suggested_platform_id: int | None = None
    suggested_game_id: int | None = None


@dataclass(frozen=True, slots=True)
class ManualImportRequest:
    """One row in the operator's bulk-POST payload."""

    path: Path
    library_id: int | None = None
    action: Literal["import", "skip"] = "import"
    game_id_override: int | None = None


@dataclass(frozen=True, slots=True)
class ManualImportResult:
    """Per-entry outcome for the bulk endpoint."""

    path: Path
    action: Literal["import", "skip"]
    success: bool
    history_id: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    correlation_id: UUID | None = None


# ---------------------------------------------------------------------------
# Listing — pure read, no DB writes
# ---------------------------------------------------------------------------


def _walk_files(
    folder: Path, *, accepted_extensions: set[str]
) -> Iterable[Path]:
    """Walk ``folder`` recursively, yielding sorted paths whose
    extension is in the allow-list. Sorted output makes the
    operator UI deterministic across calls."""
    norm = {
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in accepted_extensions
    }

    def _emit(p: Path) -> Iterable[Path]:
        for entry in sorted(p.iterdir()):
            if entry.is_dir():
                yield from _emit(entry)
            elif entry.is_file() and entry.suffix.lower() in norm:
                yield entry

    return _emit(folder)


async def list_candidates(
    *,
    session: "AsyncSession",
    folder: Path,
    accepted_extensions: set[str],
) -> list[ManualImportListing]:
    """Build the manual-import grid for ``folder``.

    Walks the folder, parses each file's basename through the
    canonical dispatcher, and looks up:
      * The platform when the parser hints one.
      * The Game by case-insensitive title match (single-result
        gate — multi-match → no suggestion, the operator triages).

    The returned list is ordered by walk order (alphabetical by
    path) so the UI's pagination stays stable across reloads.
    """
    if not folder.exists() or not folder.is_dir():
        return []

    dispatcher = default_dispatcher()
    out: list[ManualImportListing] = []

    for path in _walk_files(folder, accepted_extensions=accepted_extensions):
        try:
            size_bytes = path.stat().st_size
        except OSError:
            continue

        parsed = dispatcher.parse(path.name)
        suggested_platform_id: int | None = None
        suggested_game_id: int | None = None

        if parsed.title and parsed.confidence >= _LISTING_CONFIDENCE_FLOOR:
            platform_slug = (
                parsed.extra.get("platform_slug") if parsed.extra else None
            )
            if platform_slug:
                suggested_platform_id = (
                    await session.execute(
                        select(Platform.id).where(
                            Platform.slug == platform_slug
                        )
                    )
                ).scalar_one_or_none()
                if suggested_platform_id is not None:
                    suggested_platform_id = int(suggested_platform_id)

            title_query = select(Game.id).where(
                func.lower(Game.title) == parsed.title.lower()
            )
            if suggested_platform_id is not None:
                title_query = title_query.where(
                    Game.platform_id == suggested_platform_id
                )
            game_matches = (
                await session.execute(title_query.limit(2))
            ).scalars().all()
            if len(game_matches) == 1:
                suggested_game_id = int(game_matches[0])

        out.append(
            ManualImportListing(
                path=path,
                size_bytes=size_bytes,
                parsed_title=parsed.title or None,
                parsed_convention=(
                    parsed.convention.value
                    if parsed.confidence >= _LISTING_CONFIDENCE_FLOOR
                    else None
                ),
                parsed_regions=parsed.regions,
                parsed_languages=parsed.languages,
                suggested_platform_id=suggested_platform_id,
                suggested_game_id=suggested_game_id,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Bulk import — delegates per-entry to spec 008's run_import
# ---------------------------------------------------------------------------


async def bulk_import(
    *,
    sessionmaker: "async_sessionmaker",
    entries: Sequence[ManualImportRequest],
    imported_by: str = "manual",
) -> list[ManualImportResult]:
    """Process ``entries`` one at a time.

    Per-entry semantics:

    * ``action='skip'`` — write a successful skip outcome with no
      orchestrator invocation. The operator's "I don't want this"
      decision is still audited in the result list (FR-022).
    * ``action='import'`` — call :func:`run_import` with a fresh
      session + correlation id. The orchestrator's audit-only
      path parks the file as ``match:no_game`` today; once the
      full happy path lands, this same call exercises it.

    Per-entry exceptions are isolated — one failure doesn't drop
    the rest of the batch. The result list is in the same order
    as ``entries``.
    """
    results: list[ManualImportResult] = []

    for entry in entries:
        if entry.action == "skip":
            results.append(
                ManualImportResult(
                    path=entry.path,
                    action="skip",
                    success=True,
                )
            )
            continue

        correlation_id = uuid4()
        context = ImportContext(
            source_path=entry.path,
            correlation_id=correlation_id,
            imported_via="manual",
            imported_by=imported_by,
            library_id=entry.library_id,
        )
        try:
            async with sessionmaker() as session:
                outcome = await run_import(context, session=session)
            results.append(
                ManualImportResult(
                    path=entry.path,
                    action="import",
                    success=outcome.success,
                    history_id=outcome.history_id,
                    error_code=(
                        outcome.rejection_reason.value
                        if outcome.rejection_reason is not None
                        else None
                    ),
                    error_message=outcome.error_msg,
                    correlation_id=correlation_id,
                )
            )
        except Exception as exc:
            # Per-entry isolation per FR-024 — one bad file can't
            # take down the batch.
            results.append(
                ManualImportResult(
                    path=entry.path,
                    action="import",
                    success=False,
                    error_code="manual_import_exception",
                    error_message=str(exc),
                    correlation_id=correlation_id,
                )
            )

    return results


__all__ = [
    "ManualImportListing",
    "ManualImportRequest",
    "ManualImportResult",
    "bulk_import",
    "list_candidates",
]
