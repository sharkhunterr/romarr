"""Manual-import entry point for the orchestrator (slice 83).

The orchestrator's `run_import` is the full 13-step pipeline.
This module ships a focused subset for the **manual flow**:
the operator has already chosen the destination and the target
Release (e.g. via ``POST /api/v3/rom/unidentified/{id}/match``),
so identification + extraction + profile-gate are all skipped.
The work that remains:

  1. Hash the source if the caller didn't precompute the
     :class:`HashResult`.
  2. Coalesce check via :func:`find_existing_dump` —
     short-circuit when the operator re-confirms an
     already-imported dump.
  3. Persist the new :class:`Dump` + transition the
     :class:`Release` (delegates to spec 008's
     :func:`persist_dump` step — same code that the future
     full orchestrator will call).
  4. Record the success row via :func:`make_success_outcome`.
  5. Return the :class:`ImportOutcome`.

The function does NOT move the file on disk — manual flow
assumes the file already lives at ``dest_path`` (operator
copied it themselves, or the orchestrator's MOVE step ran
upstream). For automatic flow the full
:func:`romarr.importer.orchestrator.run_import` will compose
the MOVE step before calling persist_dump.

Caller commits the session — leaves transaction management to
the API layer / orchestrator wrapper.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from romarr.identification.hasher import Hasher
from romarr.importer._idempotency import find_existing_dump
from romarr.importer._outcome import make_success_outcome
from romarr.importer.steps.db_update import persist_dump

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.identification.hasher import HashResult
    from romarr.importer.types import ImportContext, ImportOutcome


_ImportedVia = Literal["automatic", "manual", "rss", "api", "webhook"]


async def manual_import_known(
    *,
    session: AsyncSession,
    context: ImportContext,
    release_id: int,
    game_id: int,
    dest_path: Path,
    file_format: str,
    original_filename: str,
    hashes: HashResult | None = None,
    dat_verified: bool = False,
    dat_source: str | None = None,
    dat_entry_id: int | None = None,
    keep_dump_history: bool = False,
    confidence: float = 1.0,
) -> ImportOutcome:
    """Manual-flow import: register a known file at ``dest_path``
    against ``release_id`` + ``game_id``.

    Returns the :class:`ImportOutcome` — `coalesced=True` when
    the operator re-confirms an existing dump,
    `coalesced=False` when a fresh Dump row was inserted.

    `confidence` defaults to 1.0 because manual flow is
    operator-confirmed; callers can override (e.g. for
    auto-promotions from a high-confidence cascade match
    that didn't quite clear the threshold).
    """
    started_at = datetime.now(UTC)

    # 1. Hash if not precomputed. The hasher is sync + CPU-bound
    # so it runs in a worker thread to keep the orchestrator's
    # event loop responsive (FR-014 — dump-imports never block
    # the bus).
    if hashes is None:
        hashes = await asyncio.to_thread(Hasher().hash_path, dest_path)

    # 2. Coalesce check. find_existing_dump's case-insensitive
    # comparison absorbs any lower/upper SHA-1 quirks.
    existing = await find_existing_dump(
        session=session,
        sha1=hashes.sha1,
        release_id=release_id,
    )
    if existing is not None:
        duration_ms = _elapsed_ms(started_at)
        return await make_success_outcome(
            session=session,
            context=context,
            started_at=started_at,
            duration_ms=duration_ms,
            dest_path=existing.path,
            game_id=game_id,
            release_id=release_id,
            dump_id=existing.id,
            source_hash_sha1=hashes.sha1,
            confidence=confidence,
            coalesced=True,
            warning=None,
        )

    # 3. Persist a fresh Dump + transition the Release. Mirrors
    # what the full orchestrator's DBUPDATE step will call
    # post-MOVE.
    imported_via: _ImportedVia = _coerce_imported_via(context.imported_via)
    dump = await persist_dump(
        session=session,
        release_id=release_id,
        dump_path=dest_path,
        original_filename=original_filename,
        hashes=hashes,
        file_format=file_format,
        dat_verified=dat_verified,
        dat_source=dat_source,
        dat_entry_id=dat_entry_id,
        imported_via=imported_via,
        imported_by=context.imported_by,
        keep_dump_history=keep_dump_history,
    )

    duration_ms = _elapsed_ms(started_at)
    return await make_success_outcome(
        session=session,
        context=context,
        started_at=started_at,
        duration_ms=duration_ms,
        dest_path=str(dest_path),
        game_id=game_id,
        release_id=release_id,
        dump_id=dump.id,
        source_hash_sha1=hashes.sha1,
        confidence=confidence,
        coalesced=False,
    )


def _elapsed_ms(started_at: datetime) -> int:
    delta = datetime.now(UTC) - started_at
    return max(0, int(delta.total_seconds() * 1000))


def _coerce_imported_via(value: str) -> _ImportedVia:
    """Narrow the wider :class:`ImportContext.imported_via` to
    the persist_dump literal. The full enum + literal already
    agree by construction; this helper just satisfies the type
    checker without losing runtime safety."""
    valid: tuple[_ImportedVia, ...] = (
        "automatic",
        "manual",
        "rss",
        "api",
        "webhook",
    )
    if value in valid:
        return value  # type: ignore[return-value]
    return "manual"


__all__ = ["manual_import_known"]
