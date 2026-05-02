"""Unidentified-dump endpoints — `/api/v3/rom/unidentified*`.

  * GET    /api/v3/rom/unidentified                — list (any authenticated user)
  * POST   /api/v3/rom/unidentified/{id}/match     — admin; operator-confirmed
                                                     manual import (slice 84)
  * DELETE /api/v3/rom/unidentified/{id}           — admin; **does NOT delete
                                                     the source file** (FR-038)
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.domain.models import Game, Release, UnidentifiedDump
from romarr.identification.hasher import HashResult
from romarr.importer._manual import manual_import_known
from romarr.importer.schemas import (
    ImportHistoryRead,
    ManualMatchRequest,
    UnidentifiedDumpRead,
)

router = APIRouter(prefix="/api/v3/rom/unidentified", tags=["Importer"])


@router.get(
    "",
    response_model=list[UnidentifiedDumpRead],
    summary="List unidentified dumps (any authenticated user).",
)
async def list_unidentified(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    library_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UnidentifiedDumpRead]:
    stmt = select(UnidentifiedDump).order_by(
        UnidentifiedDump.discovered_at.desc()
    )
    if library_id is not None:
        stmt = stmt.where(UnidentifiedDump.library_id == library_id)
    stmt = stmt.limit(limit).offset(offset)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        UnidentifiedDumpRead.model_validate(r, from_attributes=True)
        for r in rows
    ]


@router.post(
    "/{entry_id}/match",
    response_model=ImportHistoryRead,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Match an unidentified dump to a Game + Release and import it "
        "(admin only). Mirrors the manual-flow `import_known` "
        "orchestrator surface (slice 83): hash + coalesce-check + "
        "persist Dump + record import_history."
    ),
)
async def match_unidentified(
    entry_id: int,
    payload: ManualMatchRequest,
    admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImportHistoryRead:
    # 1. Load the unidentified row.
    row = (
        await db.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.id == entry_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "unidentified_dump_not_found",
                "errorCode": "not_found",
            },
        )

    # 2. release_id is mandatory for the manual-match flow — the
    # operator picks the target Release explicitly so the
    # importer doesn't have to guess. A future slice may add
    # "fall back to the Game's first wanted Release" but that
    # ambiguity belongs in a UI confirmation, not in the API.
    if payload.release_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errorMessage": "release_id is required for manual match",
                "errorCode": "release_id_required",
            },
        )

    # 3. Verify Game + Release exist + agree (the Release must
    # belong to the Game the operator named — guards against
    # operator typos that would otherwise persist a confusing
    # cross-Game association).
    game = (
        await db.execute(select(Game).where(Game.id == payload.game_id))
    ).scalar_one_or_none()
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"game_id={payload.game_id} not found",
                "errorCode": "game_not_found",
            },
        )
    release = (
        await db.execute(
            select(Release).where(Release.id == payload.release_id)
        )
    ).scalar_one_or_none()
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"release_id={payload.release_id} not found",
                "errorCode": "release_not_found",
            },
        )
    if release.game_id != payload.game_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": (
                    f"release_id={payload.release_id} belongs to "
                    f"game_id={release.game_id}, not {payload.game_id}"
                ),
                "errorCode": "release_game_mismatch",
            },
        )

    # 4. Build the ImportContext for audit trail.
    source_path = Path(row.path)
    # Avoid an Importer cycle: import the value type lazily.
    from romarr.importer.types import ImportContext

    context = ImportContext(
        source_path=source_path,
        correlation_id=uuid4(),
        imported_via="manual",
        imported_by=admin.username,
    )

    # 5. Reuse the unidentified row's hashes when present —
    # they were computed by the upstream IDENTIFY step. Only
    # all-three hashes count as a usable HashResult; otherwise
    # let manual_import_known re-hash the source from disk.
    precomputed = _hashes_from_unidentified(row)

    # 6. Run the manual-import flow. The destination is the
    # source path itself — manual match is "register what's
    # already on disk", not "move-and-rename".
    outcome = await manual_import_known(
        session=db,
        context=context,
        release_id=payload.release_id,
        game_id=payload.game_id,
        dest_path=source_path,
        file_format=_format_from_path(source_path),
        original_filename=source_path.name,
        hashes=precomputed,
    )

    # 7. Drop the unidentified row — manual triage is done.
    await db.delete(row)
    await db.commit()

    # 8. Project the persisted ImportHistory into the read shape.
    from romarr.importer.models import ImportHistory  # noqa: PLC0415 — late import

    history = (
        await db.execute(
            select(ImportHistory).where(ImportHistory.id == outcome.history_id)
        )
    ).scalar_one()
    return ImportHistoryRead.model_validate(history, from_attributes=True)


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Delete an unidentified-dump row (admin only). The source "
        "file on disk is NOT removed (FR-038)."
    ),
)
async def delete_unidentified(
    entry_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    row = (
        await db.execute(
            select(UnidentifiedDump).where(UnidentifiedDump.id == entry_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "unidentified_dump_not_found",
                "errorCode": "not_found",
            },
        )
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _hashes_from_unidentified(row: UnidentifiedDump) -> HashResult | None:
    """Project a recorded UnidentifiedDump back into a HashResult
    when all three (crc32 + md5 + sha1) are present. The
    foundation's IDENTIFY step writes them as a unit, so partial
    persistence shouldn't happen — we still guard against it
    rather than handing manual_import_known a half-empty record."""
    if row.crc32 is None or row.md5 is None or row.sha1 is None:
        return None
    return HashResult(
        crc32=row.crc32,
        md5=row.md5,
        sha1=row.sha1,
        sha256=None,
        size_bytes=row.size_bytes,
    )


def _format_from_path(path: Path) -> str:
    """Extract the file-format string the persist_dump step
    writes onto Dump.format. Mirrors the convention used by the
    full orchestrator's HASH/EXTRACT outputs (lowercase suffix
    sans leading dot, ``raw`` when the suffix is empty)."""
    suffix = path.suffix.lstrip(".").lower()
    return suffix if suffix else "raw"


__all__ = ["router"]
