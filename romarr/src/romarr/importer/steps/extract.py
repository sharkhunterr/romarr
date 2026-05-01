"""Extract step (FR-004 / FR-004a / FR-005 / FR-006 / pipeline step 2).

Recursively extracts ``.zip``, ``.7z``, and ``.rar`` archives up
to a configurable depth (3 by default) into a destination
directory. Three independent defenses run in parallel:

  1. **Depth limit** (FR-004): nested archives are extracted
     recursively up to ``max_depth=3``. Deeper nesting raises
     :class:`ExtractError` with reason
     ``extract:depth-exceeded``.
  2. **Bomb defense** (FR-004a): cumulative uncompressed output
     is capped at ``max(4 x compressed_size, 5 GiB)`` and
     enforced **incrementally** as bytes are written. On
     overrun the extractor aborts, removes the partial output,
     and raises :class:`ExtractError` with reason
     ``extract:bomb-detected``.
  3. **Idempotent skip** (FR-006): a sentinel file
     ``.romarr-extracted-from-<sha1[:16]>`` recorded inside the
     dest directory carries the source archive's SHA-1; a
     subsequent extract that finds a matching sentinel returns
     immediately without re-extracting.

The orchestrator owns the source-archive lifecycle (FR-005 —
``preserve_archive`` toggle); this step focuses on producing a
clean extracted directory.

The extractor runs the format-specific work inside
:func:`asyncio.to_thread` because ``zipfile`` / ``py7zr`` /
``rarfile`` are all synchronous and CPU-bound.
"""

from __future__ import annotations

import asyncio
import contextlib
import zipfile
from dataclasses import dataclass
from pathlib import Path

import py7zr
import rarfile

from romarr.identification.hasher import Hasher
from romarr.importer.errors import ExtractError
from romarr.importer.types import RejectionReason

_DEFAULT_MAX_DEPTH = 3
_BOMB_FACTOR = 4
_BOMB_FLOOR_BYTES = 5 * 1024**3  # 5 GiB
_ARCHIVE_SUFFIXES = frozenset({".zip", ".7z", ".rar"})
_SENTINEL_PREFIX = ".romarr-extracted-from-"


# ---------------------------------------------------------------------------
# Result type


@dataclass(frozen=True)
class ExtractResult:
    """Outcome of one :func:`extract` call.

    ``archive_was_processed`` is ``False`` when the idempotent
    skip fired (FR-006). ``extracted_paths`` lists every file
    written; for a coalesced re-run this is the existing
    on-disk content.
    """

    extracted_paths: tuple[Path, ...]
    archive_was_processed: bool
    bytes_written: int


# ---------------------------------------------------------------------------
# Public API


async def extract(
    *,
    archive_path: Path,
    dest_dir: Path,
    depth: int = 0,
    max_depth: int = _DEFAULT_MAX_DEPTH,
) -> ExtractResult:
    """Extract ``archive_path`` to ``dest_dir``.

    Recurses into nested archives discovered in the extracted
    output, up to ``max_depth``. ``depth`` tracks the current
    depth across recursive calls; the orchestrator passes
    ``depth=0`` and the function bumps it for each nested call.

    Raises :class:`ExtractError` on:
      * unsupported archive format,
      * corrupt archive,
      * depth-exceeded,
      * bomb-detected.
    """
    if depth > max_depth:
        raise ExtractError(
            f"nested archive depth {depth} exceeds max {max_depth}",
            rejection_reason=RejectionReason.EXTRACT_DEPTH_EXCEEDED.value,
        )

    suffix = archive_path.suffix.lower()
    if suffix not in _ARCHIVE_SUFFIXES:
        raise ExtractError(
            f"unsupported archive format: {suffix}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        )

    sentinel = _sentinel_path(archive_path, dest_dir)
    if sentinel.exists() and dest_dir.exists():
        existing = tuple(sorted(p for p in dest_dir.rglob("*") if p.is_file()))
        return ExtractResult(
            extracted_paths=existing,
            archive_was_processed=False,
            bytes_written=0,
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    cap_bytes = max(_BOMB_FACTOR * archive_path.stat().st_size, _BOMB_FLOOR_BYTES)

    try:
        bytes_written = await asyncio.to_thread(
            _extract_one, archive_path, dest_dir, cap_bytes
        )
    except ExtractError:
        await asyncio.to_thread(_cleanup_dir, dest_dir)
        raise

    extracted = sorted(p for p in dest_dir.rglob("*") if p.is_file())

    # Recursively unpack any nested archives discovered in the
    # extraction output. Depth bumps once per level.
    nested_archives = [
        p for p in extracted if p.suffix.lower() in _ARCHIVE_SUFFIXES
    ]
    for nested in nested_archives:
        nested_dest = nested.with_suffix(nested.suffix + ".extracted")
        nested_result = await extract(
            archive_path=nested,
            dest_dir=nested_dest,
            depth=depth + 1,
            max_depth=max_depth,
        )
        bytes_written += nested_result.bytes_written

    # Re-walk after nested extractions so the result lists every
    # file the caller can see.
    extracted = sorted(p for p in dest_dir.rglob("*") if p.is_file())

    # Mark the dest as extracted-from-this-archive (FR-006).
    sentinel.write_text(_archive_sha1(archive_path))

    return ExtractResult(
        extracted_paths=tuple(extracted),
        archive_was_processed=True,
        bytes_written=bytes_written,
    )


# ---------------------------------------------------------------------------
# Internals


def _sentinel_path(archive_path: Path, dest_dir: Path) -> Path:
    sha1_short = _archive_sha1(archive_path)[:16]
    return dest_dir / f"{_SENTINEL_PREFIX}{sha1_short}"


def _archive_sha1(archive_path: Path) -> str:
    return Hasher().hash_path(archive_path).sha1


def _cleanup_dir(dest_dir: Path) -> None:
    """Remove every regular file under ``dest_dir`` so a failed
    extraction doesn't leave half-written bytes around. The
    directory itself remains so the caller can re-attempt
    inside it."""
    if not dest_dir.exists():
        return
    for entry in dest_dir.rglob("*"):
        if entry.is_file():
            with contextlib.suppress(FileNotFoundError):
                entry.unlink()


def _extract_one(
    archive_path: Path, dest_dir: Path, cap_bytes: int
) -> int:
    """Synchronous extraction of one archive (called via
    :func:`asyncio.to_thread`). Returns total bytes written.
    Raises :class:`ExtractError` on bomb / corruption."""
    suffix = archive_path.suffix.lower()
    if suffix == ".zip":
        return _extract_zip(archive_path, dest_dir, cap_bytes)
    if suffix == ".7z":
        return _extract_7z(archive_path, dest_dir, cap_bytes)
    if suffix == ".rar":
        return _extract_rar(archive_path, dest_dir, cap_bytes)
    raise ExtractError(  # pragma: no cover — guarded above
        f"unsupported format: {suffix}",
        rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
    )


def _extract_zip(
    archive_path: Path, dest_dir: Path, cap_bytes: int
) -> int:
    try:
        zf = zipfile.ZipFile(archive_path, "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ExtractError(
            f"corrupt zip {archive_path.name}: {exc}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        ) from exc

    total = 0
    try:
        for member in zf.infolist():
            # Skip directory entries; the dest directory is created
            # implicitly when its first file is written. Symlinks
            # (``external_attr & 0o120000``) are dropped — zipfile's
            # ``open()`` already refuses to follow them, but we belt-
            # and-braces by skipping the entry entirely.
            if member.is_dir() or _is_symlink_zip_entry(member):
                continue
            target = _safe_join(dest_dir, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, target.open("wb") as dst:
                total += _stream_with_cap(src, dst, cap_bytes - total)
    except ExtractError:
        raise
    except OSError as exc:
        raise ExtractError(
            f"zip extraction failed: {exc}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        ) from exc
    finally:
        zf.close()
    return total


def _is_symlink_zip_entry(member: zipfile.ZipInfo) -> bool:
    """ZIP symlinks have the unix ``S_IFLNK`` (0o120000) high
    bits set in ``external_attr``. We skip them outright to
    avoid path-traversal classes of attack."""
    return (member.external_attr >> 16) & 0o170000 == 0o120000


def _extract_7z(
    archive_path: Path, dest_dir: Path, cap_bytes: int
) -> int:
    """py7zr doesn't expose a streaming-write API like
    :class:`zipfile.ZipFile.open`; we pre-validate the
    cumulative uncompressed size against ``cap_bytes`` from
    the archive's metadata and only extract once we've proven
    the archive can't bomb us. Path-traversal members are
    also pre-rejected before any bytes hit disk."""
    try:
        archive = py7zr.SevenZipFile(archive_path, "r")
    except py7zr.exceptions.Bad7zFile as exc:
        raise ExtractError(
            f"corrupt 7z {archive_path.name}: {exc}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        ) from exc
    except OSError as exc:
        raise ExtractError(
            f"7z open failed: {exc}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        ) from exc

    try:
        infos = archive.list()
        total = 0
        for info in infos:
            if info.is_directory:
                continue
            uncompressed = info.uncompressed or 0
            total += uncompressed
            if total > cap_bytes:
                raise ExtractError(
                    f"7z uncompressed expansion exceeds cap "
                    f"({total} > {cap_bytes})",
                    rejection_reason=RejectionReason.EXTRACT_BOMB_DETECTED.value,
                )
            # Pre-validate path-traversal before any bytes land.
            _safe_join(dest_dir, info.filename)

        archive.reset()
        archive.extractall(path=dest_dir)
        # py7zr propagates file modes from the archive's metadata
        # which can be 0o000 for ``writestr``-built archives. Force
        # owner-read on every extracted file so downstream steps
        # (HASH, MOVE) can read it.
        for entry in dest_dir.rglob("*"):
            if entry.is_file():
                with contextlib.suppress(OSError):
                    entry.chmod(entry.stat().st_mode | 0o400)
        return total
    except ExtractError:
        raise
    except (py7zr.exceptions.Bad7zFile, OSError) as exc:
        raise ExtractError(
            f"7z extraction failed: {exc}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        ) from exc
    finally:
        archive.close()


def _extract_rar(
    archive_path: Path, dest_dir: Path, cap_bytes: int
) -> int:
    try:
        rf = rarfile.RarFile(archive_path)
    except rarfile.BadRarFile as exc:
        raise ExtractError(
            f"corrupt rar {archive_path.name}: {exc}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        ) from exc

    total = 0
    try:
        for member in rf.infolist():
            if member.is_dir():
                continue
            target = _safe_join(dest_dir, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with rf.open(member) as src, target.open("wb") as dst:
                total += _stream_with_cap(src, dst, cap_bytes - total)
    except ExtractError:
        raise
    except (rarfile.Error, OSError) as exc:
        raise ExtractError(
            f"rar extraction failed: {exc}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        ) from exc
    finally:
        rf.close()
    return total


def _stream_with_cap(
    src: object, dst: object, remaining_budget: int
) -> int:
    """Stream ``src`` → ``dst`` 64 KB at a time, raising
    :class:`ExtractError` (``extract:bomb-detected``) the moment
    the cumulative write exceeds ``remaining_budget``. Returns
    bytes written."""
    chunk_size = 64 * 1024
    written = 0
    while True:
        chunk = src.read(chunk_size)  # type: ignore[attr-defined]
        if not chunk:
            return written
        if written + len(chunk) > remaining_budget:
            # Don't bother flushing the partial chunk — the
            # caller's outer try/except cleans up the partial
            # dest directory.
            raise ExtractError(
                f"uncompressed expansion exceeds cap ({remaining_budget} "
                f"bytes remaining); aborting extraction",
                rejection_reason=RejectionReason.EXTRACT_BOMB_DETECTED.value,
            )
        dst.write(chunk)  # type: ignore[attr-defined]
        written += len(chunk)


def _safe_join(base: Path, member: str) -> Path:
    """Defensive path-traversal check. ``zipfile`` / ``py7zr`` /
    ``rarfile`` already sanitise on most platforms, but we
    re-check so a member like ``../../etc/passwd`` lands inside
    ``base`` rather than escaping it."""
    target = (base / member).resolve()
    base_resolved = base.resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError as exc:
        raise ExtractError(
            f"archive member escapes destination: {member!r}",
            rejection_reason=RejectionReason.EXTRACT_BAD_ARCHIVE.value,
        ) from exc
    return target


__all__ = ["ExtractResult", "extract"]
