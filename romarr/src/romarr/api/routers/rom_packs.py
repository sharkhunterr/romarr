"""ROM content-pack management — /api/v3/rom-pack.

A *content pack* is a downloadable archive holding many ROMs (a
No-Intro full set, an archive.org romset, a curated bundle). This
router is the operator-facing CRUD surface plus the on-demand
``/ingest`` trigger that hands a pack to
:func:`romarr.rom_packs.ingest.ingest_rom_pack`.

The ingest is long-running (download → extract → batch-import),
so ``/ingest`` fires it as a detached ``asyncio`` task on the
app's sessionmaker and returns immediately — the row's
``status`` + counter fields are the progress channel the
Settings → Content Packs page polls.

Distinct from ``/api/v3/platform-pack`` — that's *platform
metadata*; this is actual ROM content.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import delete, select

# ``async_sessionmaker`` is imported at runtime — FastAPI
# introspects the ``Depends(get_sessionmaker)`` annotation to
# build the route signature, so the symbol must be live.
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.api.dependencies import (
    get_db,
    get_sessionmaker,
    require_admin,
    require_readonly,
)
from romarr.auth import Principal
from romarr.domain.models import Platform, RomPack, RomPackItem
from romarr.rom_packs.ingest import ingest_rom_pack

_log = logging.getLogger(__name__)

_SourceKind = Literal["url", "grab"]
_PackStatus = Literal[
    "pending",
    "downloading",
    "extracting",
    "importing",
    "awaiting_triage",
    "done",
    "failed",
]
_ItemStatus = Literal["imported", "unmatched", "parked", "deleted", "failed"]

# Statuses from which a (re-)ingest is allowed. Refusing mid-run
# starts keeps two ingest tasks off the same pack.
_INGESTABLE = frozenset({"pending", "awaiting_triage", "done", "failed"})


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RomPackItemRead(_Base):
    id: int
    rom_pack_id: int
    original_filename: str
    extracted_path: str | None
    size_bytes: int | None
    crc32: str | None
    md5: str | None
    sha1: str | None
    status: _ItemStatus
    dat_entry_id: int | None
    game_id: int | None
    dump_id: int | None
    error_msg: str | None
    created_at: datetime
    updated_at: datetime


class RomPackRead(_Base):
    id: int
    name: str
    source_kind: _SourceKind
    url: str | None
    download_client_id: int | None
    download_client_native_id: str | None
    platform_id: int | None
    platform_slug: str | None = None
    platform_name: str | None = None
    max_size_bytes: int | None
    status: _PackStatus
    downloaded_path: str | None
    size_bytes: int | None
    total_files: int
    imported_count: int
    unmatched_count: int
    parked_count: int
    failed_count: int
    last_error: str | None
    last_ingest_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RomPackCreate(_Base):
    """Slice 460 only exposes ``url``-sourced packs; ``grab``
    packs are created by the watcher in slice 463."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    url: HttpUrl
    platform_id: int | None = None
    max_size_bytes: Annotated[int | None, Field(default=None, gt=0)] = None


class RomPackUpdate(_Base):
    name: Annotated[
        str | None, Field(default=None, min_length=1, max_length=255)
    ] = None
    url: HttpUrl | None = None
    platform_id: int | None = None
    max_size_bytes: Annotated[int | None, Field(default=None, gt=0)] = None


router = APIRouter(prefix="/api/v3/rom-pack", tags=["ROM Packs"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_read(row: RomPack, platform: Platform | None = None) -> RomPackRead:
    return RomPackRead.model_validate(
        {
            **{c.name: getattr(row, c.name) for c in row.__table__.columns},
            "platform_slug": platform.slug if platform else None,
            "platform_name": platform.name if platform else None,
        }
    )


async def _load_pack(db: AsyncSession, pack_id: int) -> RomPack:
    row = (
        await db.execute(select(RomPack).where(RomPack.id == pack_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "rom_pack_not_found",
                "errorCode": "not_found",
            },
        )
    return row


async def _platform_for(
    db: AsyncSession, platform_id: int | None
) -> Platform | None:
    if platform_id is None:
        return None
    return (
        await db.execute(
            select(Platform).where(Platform.id == platform_id)
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[RomPackRead],
    summary="List ROM content packs (any authenticated user).",
)
async def list_packs(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RomPackRead]:
    rows = (
        await db.execute(
            select(RomPack, Platform)
            .outerjoin(Platform, Platform.id == RomPack.platform_id)
            .order_by(RomPack.created_at.desc())
        )
    ).all()
    return [_to_read(pack, plat) for pack, plat in rows]


@router.get(
    "/{pack_id}",
    response_model=RomPackRead,
    summary="One ROM content pack (any authenticated user).",
)
async def get_pack(
    pack_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RomPackRead:
    row = await _load_pack(db, pack_id)
    return _to_read(row, await _platform_for(db, row.platform_id))


@router.get(
    "/{pack_id}/items",
    response_model=list[RomPackItemRead],
    summary="Per-file outcomes for one pack (any authenticated user).",
)
async def list_pack_items(
    pack_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: _ItemStatus | None = None,
) -> list[RomPackItemRead]:
    """The triage modal (slice 462) pulls this with
    ``status_filter=unmatched`` to render the per-file picker."""
    await _load_pack(db, pack_id)  # 404 if the pack is gone
    stmt = select(RomPackItem).where(RomPackItem.rom_pack_id == pack_id)
    if status_filter is not None:
        stmt = stmt.where(RomPackItem.status == status_filter)
    rows = (
        await db.execute(stmt.order_by(RomPackItem.original_filename.asc()))
    ).scalars().all()
    return [RomPackItemRead.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=RomPackRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new URL-sourced ROM content pack (admin only).",
)
async def create_pack(
    payload: RomPackCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RomPackRead:
    platform = await _platform_for(db, payload.platform_id)
    if payload.platform_id is not None and platform is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "platform_not_found",
                "errorCode": "not_found",
            },
        )
    row = RomPack(
        name=payload.name,
        source_kind="url",
        url=str(payload.url),
        platform_id=payload.platform_id,
        max_size_bytes=payload.max_size_bytes,
        status="pending",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_read(row, platform)


@router.put(
    "/{pack_id}",
    response_model=RomPackRead,
    summary="Update a ROM content pack (admin only).",
)
async def update_pack(
    pack_id: int,
    payload: RomPackUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RomPackRead:
    row = await _load_pack(db, pack_id)
    fields = payload.model_dump(exclude_unset=True)
    if "platform_id" in fields:
        platform = await _platform_for(db, fields["platform_id"])
        if fields["platform_id"] is not None and platform is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "errorMessage": "platform_not_found",
                    "errorCode": "not_found",
                },
            )
        row.platform_id = fields["platform_id"]
    if "name" in fields and fields["name"] is not None:
        row.name = fields["name"]
    if "url" in fields and fields["url"] is not None:
        row.url = str(fields["url"])
    if "max_size_bytes" in fields:
        row.max_size_bytes = fields["max_size_bytes"]
    await db.commit()
    await db.refresh(row)
    return _to_read(row, await _platform_for(db, row.platform_id))


@router.delete(
    "/{pack_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a ROM content pack + its item rows (admin only).",
)
async def delete_pack(
    pack_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Drops the ``rom_pack`` row; ``rom_pack_item`` rows cascade.
    Imported Games / Dumps stay in the Library — only the pack's
    bookkeeping is removed."""
    await db.execute(delete(RomPack).where(RomPack.id == pack_id))
    await db.commit()


@router.post(
    "/{pack_id}/ingest",
    response_model=RomPackRead,
    summary="Trigger download → extract → import for one pack (admin only).",
)
async def ingest_pack(
    pack_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    sessionmaker: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_sessionmaker)
    ],
) -> RomPackRead:
    """Fire the ingest pipeline as a detached task and return the
    row immediately. The pipeline owns its own sessions and
    drives ``status`` through downloading → … → done / failed —
    the Content Packs page polls this row for progress."""
    row = await _load_pack(db, pack_id)
    if row.status not in _INGESTABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "rom_pack_ingest_in_progress",
                "errorCode": "conflict",
                "details": f"pack is {row.status!r}; wait for it to settle",
            },
        )
    # Flip to a non-terminal status synchronously so a double
    # click can't slip a second task past the guard above.
    row.status = "pending"
    row.last_error = None
    await db.commit()
    await db.refresh(row)

    async def _run() -> None:
        try:
            await ingest_rom_pack(
                sessionmaker=sessionmaker, rom_pack_id=pack_id
            )
        except Exception:
            _log.exception("rom_pack.ingest.task_crashed id=%s", pack_id)

    asyncio.get_running_loop().create_task(_run())
    return _to_read(row, await _platform_for(db, row.platform_id))
