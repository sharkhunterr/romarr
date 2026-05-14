"""ROM content-pack ingest pipeline (slice 460).

``ingest_rom_pack`` drives one :class:`RomPack` row through its
full lifecycle:

    pending → downloading → extracting → importing
            → awaiting_triage (if any unmatched) | done | failed

Stages:

1. **Download** — stream the archive to disk in 1 MiB chunks
   (never buffered in RAM), guarded by a free-space pre-check
   and a per-pack / global size cap. ``grab``-sourced packs
   skip this — their archive is already on disk.
2. **Extract** — hand the archive to the importer's recursive
   ``extract()`` (zip / 7z / rar, bomb + depth guards).
3. **Import** — for every extracted ROM:
   - hash it, look it up in the DAT cache;
   - on a verified match → find-or-create the Game from the
     DAT entry and run the normal importer with a
     ``pre_matched_game_id`` so the ROM lands in a Library;
   - on no match → record the item ``unmatched`` and leave the
     extracted file in place for the triage modal (slice 462).

Per-file failures are isolated — one bad ROM never aborts the
pack. Every file gets exactly one :class:`RomPackItem` row.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
from sqlalchemy import select

from romarr.domain.models import DatEntry, Game, RomPack, RomPackItem
from romarr.identification.dat.manager import _resolve_authority
from romarr.identification.hasher import Hasher
from romarr.importer.orchestrator import run_import
from romarr.importer.steps.extract import extract as extract_archive
from romarr.importer.types import ImportContext
from romarr.rom_packs.config import get_or_create_rom_pack_config

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Awaited with ``(bytes_written, total_bytes_or_None)`` as the
# stream progresses — the ingest pipeline uses it to mirror a
# URL pack's transfer into ``queue_entry``.
ProgressCallback = Callable[[int, "int | None"], Awaitable[None]]


def _queue_native_id(rom_pack_id: int) -> str:
    """A URL pack streamed by Romarr mirrors itself into
    ``queue_entry`` under this synthetic native id so Activity →
    Queue shows the transfer; ``download_client_id`` stays NULL
    (slice 465)."""
    return f"rom_pack:{rom_pack_id}"

# Default ceiling for a pack download when the row carries no
# ``max_size_bytes`` override. 50 GiB comfortably fits a full
# No-Intro cartridge set; a mistyped URL pulling something
# larger trips the cap instead of the disk.
DEFAULT_MAX_PACK_BYTES = 50 * 1024 * 1024 * 1024

# Headroom we insist on having free *beyond* the archive size
# before starting a download — the archive plus its extracted
# contents both have to fit. 2x the (known) archive size, or a
# flat floor when the size is unknown up front.
_FREE_SPACE_FLOOR = 5 * 1024 * 1024 * 1024

# Extensions we treat as importable ROMs after extraction.
# Mirrors the importer's ``_ROM_SUFFIXES``; archives are
# excluded here because ``extract()`` already unwrapped them.
_ROM_SUFFIXES: frozenset[str] = frozenset({
    ".gba", ".nds", ".sfc", ".smc", ".n64", ".z64", ".v64",
    ".gb", ".gbc", ".nes", ".md", ".smd", ".iso", ".cue",
    ".bin", ".chd", ".rvz", ".pbp", ".cso", ".wbfs", ".wia",
    ".nkit", ".ciso", ".gdi", ".gcm", ".3ds", ".cia", ".nsp",
    ".xci", ".unif", ".fds", ".vb", ".min", ".sms", ".gg",
    ".vpk", ".32x",
})

_CHUNK = 1024 * 1024  # 1 MiB streaming chunk


class RomPackIngestError(Exception):
    """Fatal, pack-level ingest failure (download / extract).

    Per-file failures never raise — they're recorded on the
    individual :class:`RomPackItem` and the pack continues.
    """


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


# Throttle progress callbacks — one DB write per ~8 MiB streamed
# keeps Activity → Queue lively without hammering the session.
_PROGRESS_STEP = 8 * 1024 * 1024


async def _stream_download(
    *,
    url: str,
    dest: Path,
    max_bytes: int,
    on_progress: ProgressCallback | None = None,
) -> int:
    """Stream ``url`` to ``dest`` in chunks. Returns bytes written.

    Enforces ``max_bytes`` incrementally — a server lying about
    Content-Length can't blow past the cap. Cleans up the partial
    file on overrun.

    ``on_progress`` — when given — is awaited with
    ``(bytes_written, total_bytes_or_None)`` roughly every
    ``_PROGRESS_STEP`` bytes plus once at the end, so the caller
    can mirror the transfer into ``queue_entry``.
    """
    written = 0
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=True
    ) as client, client.stream("GET", url) as resp:
        if resp.status_code >= 400:
            raise RomPackIngestError(
                f"upstream {resp.status_code} fetching {url}"
            )
        cl = resp.headers.get("content-length")
        total = int(cl) if cl is not None and cl.isdigit() else None
        next_report = _PROGRESS_STEP
        with dest.open("wb") as fh:
            async for chunk in resp.aiter_bytes(_CHUNK):
                written += len(chunk)
                if written > max_bytes:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise RomPackIngestError(
                        f"download exceeded the {max_bytes}-byte cap "
                        f"for {url}"
                    )
                fh.write(chunk)
                if on_progress is not None and written >= next_report:
                    await on_progress(written, total)
                    next_report = written + _PROGRESS_STEP
    if on_progress is not None:
        await on_progress(written, total)
    return written


async def _upsert_queue_entry(
    sessionmaker: Callable[[], AsyncSession],
    *,
    rom_pack_id: int,
    title: str,
) -> None:
    """Create (or reset, on a re-ingest) the ``queue_entry`` mirror
    for a URL pack's transfer so it shows up in Activity → Queue.

    ``download_client_id`` stays NULL — this is a Romarr-internal
    download (slice 465); the reconciler leaves it alone and the
    ingest pipeline drives its progress."""
    # Lazy import: ``romarr.api`` eagerly pulls in the FastAPI app
    # (which imports this module's router) — a module-level
    # import here would close an import cycle at startup.
    from romarr.api.models import QueueEntry

    native_id = _queue_native_id(rom_pack_id)
    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_native_id == native_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            session.add(
                QueueEntry(
                    download_client_id=None,
                    download_client_native_id=native_id,
                    title=title,
                    state="downloading",
                    progress=0.0,
                )
            )
        else:
            row.state = "downloading"
            row.progress = 0.0
            row.error_msg = None
            row.title = title
        await session.commit()


async def _update_queue_progress(
    sessionmaker: Callable[[], AsyncSession],
    *,
    rom_pack_id: int,
    written: int,
    total: int | None,
) -> None:
    """Progress-callback body — refresh the ``queue_entry`` mirror's
    ``progress`` + ``size_bytes`` as the archive streams in."""
    from romarr.api.models import QueueEntry

    native_id = _queue_native_id(rom_pack_id)
    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_native_id == native_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.size_bytes = total
        row.progress = (
            min(1.0, written / total) if total and total > 0 else 0.0
        )
        row.last_updated_at = datetime.now(UTC)
        await session.commit()


async def _settle_queue_entry(
    sessionmaker: Callable[[], AsyncSession],
    *,
    rom_pack_id: int,
    success: bool,
    error: str | None = None,
) -> None:
    """Close out a URL pack's ``queue_entry`` mirror once the
    *download* finishes: delete it on success (the transfer is
    done — the pack page carries the extract/import story), or
    flip it to ``failed`` with the error so Activity surfaces it."""
    from romarr.api.models import QueueEntry

    native_id = _queue_native_id(rom_pack_id)
    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(QueueEntry).where(
                    QueueEntry.download_client_native_id == native_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        if success:
            await session.delete(row)
        else:
            row.state = "failed"
            row.progress = row.progress or 0.0
            row.error_msg = (error or "download failed")[:500]
            row.last_updated_at = datetime.now(UTC)
        await session.commit()


def _precheck_free_space(target: Path, archive_size_hint: int | None) -> None:
    """Raise :class:`RomPackIngestError` when ``target``'s volume
    hasn't got room for the archive + its extracted payload."""
    try:
        free = shutil.disk_usage(target).free
    except OSError as exc:  # pragma: no cover - unusual FS state
        raise RomPackIngestError(
            f"cannot stat free space on {target}: {exc}"
        ) from exc
    # Need the archive itself + its extraction. 2x the archive
    # size when we have a hint, the flat floor otherwise.
    needed = (
        archive_size_hint * 2
        if archive_size_hint
        else _FREE_SPACE_FLOOR
    )
    if free < needed:
        raise RomPackIngestError(
            f"insufficient disk space at {target}: "
            f"{free / 1e9:.1f} GB free, need ~{needed / 1e9:.1f} GB"
        )


_ARCHIVE_SUFFIXES: frozenset[str] = frozenset({".zip", ".7z", ".rar"})


async def _collect_rom_files(source: Path, extract_dir: Path) -> list[Path]:
    """Resolve a downloaded pack source into the flat list of
    importable ROM files.

    ``source`` may be a single archive, a bare ROM, or a
    directory of either — a ``grab``-sourced pack's
    ``downloaded_path`` is whatever the download client's
    ``save_path`` points at, which for a multi-file torrent is
    the torrent's top-level directory.

    Archives are unwrapped via the importer's recursive
    ``extract()`` (zip / 7z / rar, bomb + depth guards); loose
    ROMs pass through as-is.

    Per-file extraction failures are isolated — a single bad
    archive in a big romset (a ``.rar``-named non-RAR, a corrupt
    member, a split-volume part) is logged and skipped so the
    rest of the pack still imports.
    """
    sources = (
        sorted(p for p in source.rglob("*") if p.is_file())
        if source.is_dir()
        else [source]
    )

    rom_files: list[Path] = []
    for idx, path in enumerate(sources):
        suffix = path.suffix.lower()
        if suffix in _ARCHIVE_SUFFIXES:
            sub = extract_dir / f"archive_{idx}"
            sub.mkdir(parents=True, exist_ok=True)
            try:
                result = await extract_archive(
                    archive_path=path, dest_dir=sub
                )
            except Exception as exc:  # isolate per-archive
                logger.warning(
                    "rom_pack.extract_skipped path=%s: %s", path, exc
                )
                continue
            rom_files.extend(
                p
                for p in result.extracted_paths
                if p.suffix.lower() in _ROM_SUFFIXES
            )
        elif suffix in _ROM_SUFFIXES:
            rom_files.append(path)
    return rom_files


# ---------------------------------------------------------------------------
# Per-ROM import
# ---------------------------------------------------------------------------


async def _resolve_dat_match(
    session: AsyncSession, *, sha1: str, platform_id: int | None
) -> DatEntry | None:
    """Best DAT entry for ``sha1`` (CL001 authority order).

    Scoped to ``platform_id`` when the pack pins one; otherwise
    searches every platform — a multi-platform pack relies on
    the per-ROM hash to scatter ROMs to the right console.
    """
    stmt = select(DatEntry).where(DatEntry.sha1 == sha1.lower())
    if platform_id is not None:
        stmt = stmt.where(DatEntry.platform_id == platform_id)
    rows = list((await session.execute(stmt)).scalars().all())
    best = _resolve_authority(rows)
    return best.winner if best is not None else None


async def _find_or_create_game(
    session: AsyncSession, *, dat_entry: DatEntry
) -> Game:
    """Return the monitored Game for ``dat_entry``'s platform +
    canonical name, creating it when the operator doesn't track
    it yet. The auto-created Game is flagged
    ``needs_metadata_refresh`` so the aggregator enriches it
    (cover, summary, …) on the next cycle."""
    # Lazy import: ``romarr.metadata.api`` eagerly pulls in the
    # FastAPI routers, which would form an import cycle if this
    # module were imported at app-startup time.
    from romarr.metadata.api.lookup import (
        _allocate_unique_slug,
        slugify_title,
    )

    base_slug = slugify_title(dat_entry.name)
    existing = (
        await session.execute(
            select(Game).where(
                Game.platform_id == dat_entry.platform_id,
                Game.slug == base_slug,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    slug = await _allocate_unique_slug(
        session, platform_id=dat_entry.platform_id, base=base_slug
    )
    game = Game(
        platform_id=dat_entry.platform_id,
        slug=slug,
        title=dat_entry.name.strip(),
        monitored=True,
        needs_metadata_refresh=True,
    )
    session.add(game)
    await session.flush()
    logger.info(
        "rom_pack.auto_created_game id=%s title=%r platform=%s",
        game.id,
        game.title,
        dat_entry.platform_id,
    )
    return game


async def _import_one_rom(
    *,
    sessionmaker: Callable[[], AsyncSession],
    rom_pack_id: int,
    rom_path: Path,
    pack_platform_id: int | None,
) -> RomPackItem:
    """Hash + DAT-match + import one extracted ROM. Always
    returns a :class:`RomPackItem` (never raises) — caller adds
    it to the session and rolls the pack counters."""
    item = RomPackItem(
        rom_pack_id=rom_pack_id,
        original_filename=rom_path.name,
        extracted_path=str(rom_path),
    )
    try:
        hashes = Hasher().hash_path(rom_path)
        item.sha1 = hashes.sha1
        item.md5 = hashes.md5
        item.crc32 = hashes.crc32
        item.size_bytes = hashes.size_bytes
    except OSError as exc:
        item.status = "failed"
        item.error_msg = f"hash: {exc}"[:500]
        return item

    # DAT lookup + (find-or-create) Game resolution need their
    # own session; the actual import opens yet another (run_import
    # owns its transaction).
    async with sessionmaker() as session:
        dat_entry = await _resolve_dat_match(
            session, sha1=hashes.sha1, platform_id=pack_platform_id
        )
        if dat_entry is None:
            # No DAT match — leave the extracted file in place and
            # hand it to the triage modal (slice 462).
            item.status = "unmatched"
            return item
        item.dat_entry_id = dat_entry.id
        game = await _find_or_create_game(session, dat_entry=dat_entry)
        game_id = game.id
        await session.commit()

    # Run the standard importer with the resolved game pinned —
    # it creates the Release, re-verifies the DAT at import time
    # (slice 452), moves the ROM into the Library and persists
    # the Dump.
    context = ImportContext(
        source_path=rom_path,
        correlation_id=uuid4(),
        imported_via="api",
        pre_matched_game_id=game_id,
    )
    async with sessionmaker() as session:
        try:
            outcome = await run_import(context, session=session)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            item.status = "failed"
            item.error_msg = f"import: {type(exc).__name__}: {exc}"[:500]
            return item

    if outcome.success:
        item.status = "imported"
        item.game_id = game_id
        item.dump_id = getattr(outcome, "dump_id", None)
    else:
        # The importer parked it (extract failure, profile gate,
        # destination collision …). Surface it as ``parked`` so
        # the operator finds it in unidentified_dump.
        item.status = "parked"
        item.error_msg = (outcome.error_msg or "import did not succeed")[:500]
    return item


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def ingest_rom_pack(
    *,
    sessionmaker: Callable[[], AsyncSession],
    rom_pack_id: int,
    download_root: str | Path | None = None,
) -> None:
    """Drive one :class:`RomPack` through download → extract →
    import. Updates the row's ``status`` + counters as it goes;
    never raises (fatal errors land in ``status='failed'`` +
    ``last_error``).

    ``download_root`` overrides the global ``rom_pack_config``
    default — handy in tests. Production callers leave it None
    so the operator-tuned Settings value applies."""
    # ── Load + mark downloading ──────────────────────────────
    async with sessionmaker() as session:
        pack = (
            await session.execute(
                select(RomPack).where(RomPack.id == rom_pack_id)
            )
        ).scalar_one_or_none()
        if pack is None:
            logger.warning("rom_pack.ingest: id=%s not found", rom_pack_id)
            return
        config = await get_or_create_rom_pack_config(session)
        pack.status = "downloading"
        pack.last_error = None
        pack.last_ingest_at = datetime.now(UTC)
        url = pack.url
        pack_name = pack.name
        source_kind = pack.source_kind
        platform_id = pack.platform_id
        max_bytes = (
            pack.max_size_bytes
            or config.default_max_size_bytes
            or DEFAULT_MAX_PACK_BYTES
        )
        existing_path = pack.downloaded_path
        config_dir = config.download_dir
        await session.commit()

    root = Path(download_root) if download_root is not None else Path(config_dir)
    root.mkdir(parents=True, exist_ok=True)

    archive_path: Path | None = None
    try:
        # ── Download (url-sourced) ──────────────────────────
        if source_kind == "grab":
            # Slice 463 fills download_client fields; the archive
            # is already on disk.
            if not existing_path or not Path(existing_path).exists():
                raise RomPackIngestError(
                    "grab-sourced pack has no archive on disk"
                )
            archive_path = Path(existing_path)
        else:
            if not url:
                raise RomPackIngestError("url-sourced pack has no url")
            _precheck_free_space(root, None)
            suffix = Path(url.split("?")[0]).suffix or ".zip"
            archive_path = root / f"rom_pack_{rom_pack_id}{suffix}"

            # Mirror the transfer into queue_entry so the operator
            # watches it in Activity → Queue, just like a grab.
            await _upsert_queue_entry(
                sessionmaker, rom_pack_id=rom_pack_id, title=pack_name
            )

            async def _on_progress(written: int, total: int | None) -> None:
                await _update_queue_progress(
                    sessionmaker,
                    rom_pack_id=rom_pack_id,
                    written=written,
                    total=total,
                )

            try:
                written = await _stream_download(
                    url=url,
                    dest=archive_path,
                    max_bytes=max_bytes,
                    on_progress=_on_progress,
                )
            except Exception as exc:
                await _settle_queue_entry(
                    sessionmaker,
                    rom_pack_id=rom_pack_id,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            # Download done — close the Activity row; the pack
            # page carries the extract / import / triage story.
            await _settle_queue_entry(
                sessionmaker, rom_pack_id=rom_pack_id, success=True
            )

            async with sessionmaker() as session:
                pack = (
                    await session.execute(
                        select(RomPack).where(RomPack.id == rom_pack_id)
                    )
                ).scalar_one()
                pack.downloaded_path = str(archive_path)
                pack.size_bytes = written
                await session.commit()

        # ── Extract ─────────────────────────────────────────
        async with sessionmaker() as session:
            pack = (
                await session.execute(
                    select(RomPack).where(RomPack.id == rom_pack_id)
                )
            ).scalar_one()
            pack.status = "extracting"
            await session.commit()

        extract_dir = Path(
            tempfile.mkdtemp(prefix=f"rom_pack_{rom_pack_id}_", dir=str(root))
        )
        rom_files = await _collect_rom_files(archive_path, extract_dir)

        # ── Import each ROM ─────────────────────────────────
        async with sessionmaker() as session:
            pack = (
                await session.execute(
                    select(RomPack).where(RomPack.id == rom_pack_id)
                )
            ).scalar_one()
            pack.status = "importing"
            pack.total_files = len(rom_files)
            await session.commit()

        imported = unmatched = parked = failed = 0
        for rom_path in rom_files:
            item = await _import_one_rom(
                sessionmaker=sessionmaker,
                rom_pack_id=rom_pack_id,
                rom_path=rom_path,
                pack_platform_id=platform_id,
            )
            if item.status == "imported":
                imported += 1
            elif item.status == "unmatched":
                unmatched += 1
            elif item.status == "parked":
                parked += 1
            else:
                failed += 1
            async with sessionmaker() as session:
                session.add(item)
                await session.commit()

        # ── Finalise ────────────────────────────────────────
        async with sessionmaker() as session:
            pack = (
                await session.execute(
                    select(RomPack).where(RomPack.id == rom_pack_id)
                )
            ).scalar_one()
            pack.imported_count = imported
            pack.unmatched_count = unmatched
            pack.parked_count = parked
            pack.failed_count = failed
            pack.status = "awaiting_triage" if unmatched > 0 else "done"
            await session.commit()

        logger.info(
            "rom_pack.ingest done id=%s imported=%d unmatched=%d "
            "parked=%d failed=%d",
            rom_pack_id,
            imported,
            unmatched,
            parked,
            failed,
        )
    except Exception as exc:
        logger.exception("rom_pack.ingest failed id=%s", rom_pack_id)
        async with sessionmaker() as session:
            pack = (
                await session.execute(
                    select(RomPack).where(RomPack.id == rom_pack_id)
                )
            ).scalar_one_or_none()
            if pack is not None:
                pack.status = "failed"
                pack.last_error = f"{type(exc).__name__}: {exc}"[:500]
                await session.commit()
    finally:
        # Purge the downloaded archive — only when *we* fetched
        # it (url-sourced). grab-sourced archives belong to the
        # download client's lifecycle.
        if (
            archive_path is not None
            and source_kind != "grab"
            and archive_path.exists()
        ):
            archive_path.unlink(missing_ok=True)


__all__ = ["DEFAULT_MAX_PACK_BYTES", "RomPackIngestError", "ingest_rom_pack"]
