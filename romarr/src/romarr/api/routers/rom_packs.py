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
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from romarr.domain.models import (
    Game,
    Platform,
    RomPack,
    RomPackItem,
)
from romarr.importer._park import park_in_unidentified
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext
from romarr.rom_packs.config import get_or_create_rom_pack_config
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
_ImportMode = Literal["all", "dat_verified"]

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
    import_mode: _ImportMode
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
    import_mode: _ImportMode = "all"


class RomPackUpdate(_Base):
    name: Annotated[
        str | None, Field(default=None, min_length=1, max_length=255)
    ] = None
    url: HttpUrl | None = None
    platform_id: int | None = None
    max_size_bytes: Annotated[int | None, Field(default=None, gt=0)] = None
    import_mode: _ImportMode | None = None


class RomPackGrabRequest(_Base):
    """Grab one indexer result as a ROM content pack.

    Mirrors the manual-search :class:`GrabRequest` shape — the
    operator picked an exact result from a manual search — plus
    the pack metadata (``name`` / ``platform_id`` / size cap).
    The result is dispatched to a download client; the watcher
    routes the completed download to the pack ingest pipeline
    (slice 463) instead of the single-file importer."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    platform_id: int | None = None
    max_size_bytes: Annotated[int | None, Field(default=None, gt=0)] = None
    import_mode: _ImportMode = "all"
    indexer_id: int
    indexer_guid: Annotated[str, Field(min_length=1, max_length=255)]
    download_url: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1, max_length=512)]


class RomPackConfigRead(_Base):
    """Global ROM-pack defaults (the singleton config row)."""

    download_dir: str
    default_max_size_bytes: int | None
    created_at: datetime
    updated_at: datetime


class RomPackConfigUpdate(_Base):
    download_dir: Annotated[
        str | None, Field(default=None, min_length=1, max_length=2048)
    ] = None
    default_max_size_bytes: Annotated[
        int | None, Field(default=None, gt=0)
    ] = None


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
# Global config (declared before ``/{pack_id}`` so ``/config`` wins
# the route match — ``pack_id`` is an int and would 422 on "config").
# ---------------------------------------------------------------------------


@router.get(
    "/config",
    response_model=RomPackConfigRead,
    summary="Global ROM-pack defaults (any authenticated user).",
)
async def get_config(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RomPackConfigRead:
    config = await get_or_create_rom_pack_config(db)
    await db.commit()
    return RomPackConfigRead.model_validate(config)


@router.put(
    "/config",
    response_model=RomPackConfigRead,
    summary="Update the global ROM-pack defaults (admin only).",
)
async def update_config(
    payload: RomPackConfigUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RomPackConfigRead:
    config = await get_or_create_rom_pack_config(db)
    fields = payload.model_dump(exclude_unset=True)
    if "download_dir" in fields and fields["download_dir"] is not None:
        config.download_dir = fields["download_dir"].strip()
    if "default_max_size_bytes" in fields:
        config.default_max_size_bytes = fields["default_max_size_bytes"]
    await db.commit()
    await db.refresh(config)
    return RomPackConfigRead.model_validate(config)


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
        import_mode=payload.import_mode,
        status="pending",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_read(row, platform)


@router.post(
    "/grab",
    response_model=RomPackRead,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Grab one indexer result as a ROM content pack (admin only). "
        "``?force=true`` overrides the blocklist gate."
    ),
)
async def grab_pack(
    payload: RomPackGrabRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    force: Annotated[
        bool, Query(description="Override the blocklist gate")
    ] = False,
) -> RomPackRead:
    """Dispatch a chosen indexer result to a download client and
    register it as a ``grab``-sourced pack. When the download
    completes the watcher routes it to the pack ingest pipeline.

    The heavy search/dispatch deps are imported lazily — this
    router is on the app's import-time critical path and most
    requests never reach the grab branch."""
    from romarr.downloaders.models import DownloadClient
    from romarr.downloaders.routing import RoutingCandidate
    from romarr.downloaders.types import SourceKind
    from romarr.indexers.models import Indexer
    from romarr.indexers.types import SearchResult
    from romarr.search._clients import make_download_client_factory
    from romarr.search.blocklist import is_blocklisted
    from romarr.search.dispatch import DispatchStatus, dispatch_winner
    from romarr.search.dispatch_grabarr import (
        GrabarrPreResolveError,
        filter_candidates_for_magnet,
        maybe_pre_resolve,
    )
    from romarr.search.types import Candidate

    platform = await _platform_for(db, payload.platform_id)
    if payload.platform_id is not None and platform is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "platform_not_found",
                "errorCode": "not_found",
            },
        )

    result = SearchResult(
        indexer_id=payload.indexer_id,
        guid=payload.indexer_guid,
        title=payload.title,
        link=payload.download_url,
    )
    if not force:
        existing = await is_blocklisted(db, result=result)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "errorMessage": "release_blocklisted",
                    "errorCode": "blocklisted",
                    "details": existing.reason,
                },
            )

    candidate = Candidate(
        indexer_id=payload.indexer_id,
        indexer_guid=payload.indexer_guid,
        title=payload.title,
        download_url=payload.download_url,
        matched_release_id=None,
        score_breakdown=None,
        rejection=None,
        would_auto_reject=False,
    )
    routing_candidates = [
        RoutingCandidate(
            id=row.id,
            priority=row.priority,
            enabled=row.enabled,
            enable_for_torrents=row.enable_for_torrents,
            enable_for_usenet=row.enable_for_usenet,
        )
        for row in (await db.execute(select(DownloadClient))).scalars().all()
    ]
    indexer_row = (
        await db.execute(
            select(Indexer).where(Indexer.id == payload.indexer_id)
        )
    ).scalar_one_or_none()
    source_kind = (
        SourceKind.TORRENT
        if indexer_row is not None
        and indexer_row.implementation in ("torznab", "grabarr")
        else SourceKind.USENET
        if indexer_row is not None
        and indexer_row.implementation == "newznab"
        else None
    )
    indexer_pin = (
        indexer_row.download_client_id if indexer_row is not None else None
    )

    # Grabarr indexers (Minerva / Myrient et al.) hand back a
    # token URL that has to be resolved before dispatch: a
    # ``torrent_magnet`` result must route to the operator's qBit
    # row (grabarr_direct rejects magnets), a ``http_direct`` one
    # stays on the linked grabarr_direct client. ``maybe_pre_resolve``
    # is a no-op for plain torznab / newznab indexers.
    try:
        candidate, indexer_pin, grabarr_resolved = await maybe_pre_resolve(
            candidate=candidate,
            indexer_row=indexer_row,
            db=db,
        )
    except GrabarrPreResolveError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "errorMessage": "rom_pack_grab_failed",
                "errorCode": "grab_failed",
                "details": str(exc),
            },
        ) from exc
    if (
        grabarr_resolved is not None
        and grabarr_resolved.method == "torrent_magnet"
    ):
        # Drop grabarr_direct rows from the pool so qBit wins the
        # magnet by capability + priority.
        routing_candidates = await filter_candidates_for_magnet(
            candidates=routing_candidates, db=db
        )

    outcome = await dispatch_winner(
        candidate=candidate,
        candidates=routing_candidates,
        indexer_pin=indexer_pin,
        client_factory=make_download_client_factory(db),
        source_kind=source_kind,
    )
    if (
        outcome.status is not DispatchStatus.GRABBED
        or outcome.client_id is None
        or outcome.client_native_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "errorMessage": "rom_pack_grab_failed",
                "errorCode": "grab_failed",
                "details": outcome.reason or outcome.status.value,
            },
        )

    row = RomPack(
        name=payload.name,
        source_kind="grab",
        download_client_id=outcome.client_id,
        download_client_native_id=outcome.client_native_id,
        platform_id=payload.platform_id,
        max_size_bytes=payload.max_size_bytes,
        import_mode=payload.import_mode,
        status="pending",
    )
    db.add(row)
    # Mirror the grab into queue_entry so Activity → Queue shows
    # the download in flight; the watcher settles it once the
    # download completes and routes it to pack ingest.
    from romarr.api.models import QueueEntry

    db.add(
        QueueEntry(
            title=payload.title,
            download_client_id=outcome.client_id,
            download_client_native_id=outcome.client_native_id,
            state="downloading",
            progress=0.0,
        )
    )
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
    if "import_mode" in fields and fields["import_mode"] is not None:
        row.import_mode = fields["import_mode"]
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


# ---------------------------------------------------------------------------
# Triage — per-item resolution of unmatched ROMs (slice 462)
# ---------------------------------------------------------------------------


class RomPackItemAssociate(BaseModel):
    """Manual association payload — the operator picked the Game
    this unmatched ROM belongs to."""

    game_id: int


async def _load_item(
    db: AsyncSession, pack_id: int, item_id: int
) -> tuple[RomPack, RomPackItem]:
    """Load (pack, item) or 404. The item must belong to the pack."""
    pack = await _load_pack(db, pack_id)
    item = (
        await db.execute(
            select(RomPackItem).where(
                RomPackItem.id == item_id,
                RomPackItem.rom_pack_id == pack_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "rom_pack_item_not_found",
                "errorCode": "not_found",
            },
        )
    return pack, item


def _require_unmatched(item: RomPackItem) -> None:
    """Triage actions only apply to ``unmatched`` items — an
    already-resolved item is a no-op the UI shouldn't have
    offered."""
    if item.status != "unmatched":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "rom_pack_item_not_unmatched",
                "errorCode": "conflict",
                "details": f"item is {item.status!r}, not 'unmatched'",
            },
        )


def _settle_pack(pack: RomPack) -> None:
    """Flip a fully-triaged pack from ``awaiting_triage`` to
    ``done`` — every unmatched ROM has been resolved one way or
    another."""
    if pack.status == "awaiting_triage" and pack.unmatched_count <= 0:
        pack.status = "done"


@router.post(
    "/{pack_id}/items/{item_id}/associate",
    response_model=RomPackItemRead,
    summary="Manually associate an unmatched ROM with a Game (admin only).",
)
async def associate_item(
    pack_id: int,
    item_id: int,
    payload: RomPackItemAssociate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RomPackItemRead:
    """Run the standard importer against the extracted ROM with
    the operator-chosen Game pinned. On success the ROM lands in
    that Game's Library and the item flips to ``imported``."""
    pack, item = await _load_item(db, pack_id, item_id)
    _require_unmatched(item)

    game = (
        await db.execute(select(Game).where(Game.id == payload.game_id))
    ).scalar_one_or_none()
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "game_not_found",
                "errorCode": "not_found",
            },
        )
    if item.extracted_path is None or not Path(item.extracted_path).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "rom_pack_item_file_missing",
                "errorCode": "conflict",
                "details": "the extracted ROM is no longer on disk",
            },
        )

    context = ImportContext(
        source_path=Path(item.extracted_path),
        correlation_id=uuid4(),
        imported_via="api",
        pre_matched_game_id=game.id,
    )
    try:
        outcome = await run_import(context, session=db)
    except Exception as exc:
        await db.rollback()
        _log.exception(
            "rom_pack.triage.associate_failed pack=%s item=%s",
            pack_id,
            item_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errorMessage": "rom_pack_item_import_failed",
                "errorCode": "import_failed",
                "details": f"{type(exc).__name__}: {exc}",
            },
        ) from exc

    if not outcome.success:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errorMessage": "rom_pack_item_import_failed",
                "errorCode": "import_failed",
                "details": outcome.error_msg or "import did not succeed",
            },
        )

    item.status = "imported"
    item.game_id = game.id
    item.dump_id = outcome.dump_id
    item.error_msg = None
    pack.unmatched_count = max(0, pack.unmatched_count - 1)
    pack.imported_count += 1
    _settle_pack(pack)
    await db.commit()
    await db.refresh(item)
    return RomPackItemRead.model_validate(item)


@router.post(
    "/{pack_id}/items/{item_id}/park",
    response_model=RomPackItemRead,
    summary="Park an unmatched ROM in unidentified_dump (admin only).",
)
async def park_item(
    pack_id: int,
    item_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RomPackItemRead:
    """Hand the ROM to ``unidentified_dump`` so it shows up in
    Settings → Unidentified for later identification, leaving the
    extracted file in place."""
    pack, item = await _load_item(db, pack_id, item_id)
    _require_unmatched(item)
    if item.extracted_path is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "rom_pack_item_file_missing",
                "errorCode": "conflict",
                "details": "the item has no extracted path to park",
            },
        )

    await park_in_unidentified(
        session=db,
        source_path=Path(item.extracted_path),
        size_bytes=item.size_bytes or 0,
        rejection_reason="rom_pack:operator_parked",
        crc32=item.crc32,
        md5=item.md5,
        sha1=item.sha1,
        suggested_platform_id=pack.platform_id,
    )
    item.status = "parked"
    pack.unmatched_count = max(0, pack.unmatched_count - 1)
    pack.parked_count += 1
    _settle_pack(pack)
    await db.commit()
    await db.refresh(item)
    return RomPackItemRead.model_validate(item)


@router.delete(
    "/{pack_id}/items/{item_id}",
    response_model=RomPackItemRead,
    summary="Delete an unmatched ROM's extracted file (admin only).",
)
async def delete_item(
    pack_id: int,
    item_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RomPackItemRead:
    """Remove the extracted ROM from disk and mark the item
    ``deleted``. The row is kept as an audit trail of what the
    pack contained — only the file goes."""
    pack, item = await _load_item(db, pack_id, item_id)
    _require_unmatched(item)

    if item.extracted_path is not None:
        try:
            Path(item.extracted_path).unlink(missing_ok=True)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "errorMessage": "rom_pack_item_delete_failed",
                    "errorCode": "delete_failed",
                    "details": f"{type(exc).__name__}: {exc}",
                },
            ) from exc

    item.status = "deleted"
    pack.unmatched_count = max(0, pack.unmatched_count - 1)
    _settle_pack(pack)
    await db.commit()
    await db.refresh(item)
    return RomPackItemRead.model_validate(item)
