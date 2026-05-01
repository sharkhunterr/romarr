"""Extract step tests (T023-T030).

Fixture archives are programmatically built inside each test so
the repo doesn't carry binary blobs and tests stay
self-contained. ``zipfile`` / ``py7zr`` ship with the project's
deps; ``rarfile`` requires the ``unrar`` binary on PATH — we
skip the rar test when it isn't installed.
"""

from __future__ import annotations

import shutil
import zipfile
from collections.abc import Callable
from pathlib import Path

import py7zr
import pytest

from romarr.importer.errors import ExtractError
from romarr.importer.steps.extract import extract
from romarr.importer.types import RejectionReason

# ---------------------------------------------------------------------------
# Fixture builders


@pytest.fixture
def make_zip(tmp_path: Path) -> Callable[..., Path]:
    """Build a zip archive containing the given (member_name, body) pairs."""

    def _make(
        *members: tuple[str, bytes], name: str = "good.zip"
    ) -> Path:
        archive = tmp_path / "archives" / name
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w") as zf:
            for member_name, body in members:
                zf.writestr(member_name, body)
        return archive

    return _make


@pytest.fixture
def make_7z(tmp_path: Path) -> Callable[..., Path]:
    def _make(
        *members: tuple[str, bytes], name: str = "good.7z"
    ) -> Path:
        archive = tmp_path / "archives" / name
        archive.parent.mkdir(parents=True, exist_ok=True)
        with py7zr.SevenZipFile(archive, "w") as zf:
            for member_name, body in members:
                zf.writestr(body, member_name)
        return archive

    return _make


# ---------------------------------------------------------------------------
# T023 — zip happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zip_extracts_cleanly(
    tmp_path: Path,
    make_zip: Callable[..., Path],
) -> None:
    archive = make_zip(("Sonic.md", b"sonic-bytes" * 256))
    dest = tmp_path / "extracted"

    result = await extract(archive_path=archive, dest_dir=dest)

    assert result.archive_was_processed is True
    files = [p for p in result.extracted_paths if p.name == "Sonic.md"]
    assert len(files) == 1
    assert files[0].read_bytes() == b"sonic-bytes" * 256
    # Sentinel file written.
    sentinels = list(dest.glob(".romarr-extracted-from-*"))
    assert len(sentinels) == 1


# ---------------------------------------------------------------------------
# T024 — 7z happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_7z_extracts_cleanly(
    tmp_path: Path,
    make_7z: Callable[..., Path],
) -> None:
    archive = make_7z(("Sonic.md", b"sonic-7z-bytes" * 256))
    dest = tmp_path / "extracted"

    result = await extract(archive_path=archive, dest_dir=dest)

    assert result.archive_was_processed is True
    files = [p for p in result.extracted_paths if p.name == "Sonic.md"]
    assert len(files) == 1
    assert files[0].read_bytes() == b"sonic-7z-bytes" * 256


# ---------------------------------------------------------------------------
# T025 — rar happy path (skip when unrar isn't installed)
# ---------------------------------------------------------------------------


def _unrar_available() -> bool:
    """Best-effort detection of an installed unrar binary."""
    return shutil.which("unrar") is not None or shutil.which("unar") is not None


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _unrar_available(),
    reason="rarfile requires the ``unrar`` binary on PATH",
)
async def test_rar_extracts_cleanly(tmp_path: Path) -> None:
    """Build a rar archive on the fly via the host's `rar` CLI.

    Some CI environments don't have the proprietary `rar`
    encoder; in that case skip this test (the EXTRACT step
    still works against operator-provided rar files at runtime).
    """
    if shutil.which("rar") is None:
        pytest.skip("rar encoder not available on this host")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "Sonic.md").write_bytes(b"sonic-rar-bytes" * 256)

    import subprocess

    archive = tmp_path / "archives" / "good.rar"
    archive.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["rar", "a", str(archive), "Sonic.md"],
        cwd=src_dir,
        check=True,
        capture_output=True,
    )

    dest = tmp_path / "extracted"
    result = await extract(archive_path=archive, dest_dir=dest)

    assert result.archive_was_processed is True
    files = [p for p in result.extracted_paths if p.name == "Sonic.md"]
    assert len(files) == 1


# ---------------------------------------------------------------------------
# T026 — recursive zip-in-zip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recursive_zip_in_zip(tmp_path: Path) -> None:
    """An archive whose member is itself a zip extracts both
    levels in one ``extract`` call."""
    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("Sonic.md", b"sonic-inner")

    outer = tmp_path / "archives" / "outer.zip"
    outer.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(outer, "w") as zf:
        zf.write(inner, arcname="inner.zip")
    inner.unlink()  # keep tmp_path tidy

    dest = tmp_path / "extracted"
    result = await extract(archive_path=outer, dest_dir=dest)

    assert result.archive_was_processed is True
    rom_files = [p for p in result.extracted_paths if p.name == "Sonic.md"]
    assert len(rom_files) == 1
    assert rom_files[0].read_bytes() == b"sonic-inner"


# ---------------------------------------------------------------------------
# T027 — depth-exceeded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_depth_exceeded_raises(tmp_path: Path) -> None:
    """A nested-zip chain that exceeds ``max_depth`` raises
    ``extract:depth-exceeded``. We use ``max_depth=2`` against a
    3-level chain so the recursion reaches depth=3 (one over the
    cap) on the innermost call."""

    deepest = tmp_path / "level3.zip"
    with zipfile.ZipFile(deepest, "w") as zf:
        zf.writestr("Sonic.md", b"sonic")
    for level in (2, 1):
        wrapper = tmp_path / f"level{level}.zip"
        with zipfile.ZipFile(wrapper, "w") as zf:
            zf.write(deepest, arcname=deepest.name)
        deepest.unlink()
        deepest = wrapper

    dest = tmp_path / "extracted"
    with pytest.raises(ExtractError) as exc_info:
        await extract(
            archive_path=deepest,
            dest_dir=dest,
            max_depth=1,
        )
    assert (
        exc_info.value.rejection_reason
        == RejectionReason.EXTRACT_DEPTH_EXCEEDED.value
    )


# ---------------------------------------------------------------------------
# T028 — idempotent skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_re_extract_skips(
    tmp_path: Path,
    make_zip: Callable[..., Path],
) -> None:
    archive = make_zip(("Sonic.md", b"sonic"))
    dest = tmp_path / "extracted"

    first = await extract(archive_path=archive, dest_dir=dest)
    assert first.archive_was_processed is True

    second = await extract(archive_path=archive, dest_dir=dest)
    assert second.archive_was_processed is False  # coalesced
    assert second.bytes_written == 0
    assert any(p.name == "Sonic.md" for p in second.extracted_paths)


# ---------------------------------------------------------------------------
# T029 — corrupted archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupted_archive_raises(tmp_path: Path) -> None:
    archive = tmp_path / "corrupt.7z"
    archive.write_bytes(b"NOT A VALID 7Z FILE")

    with pytest.raises(ExtractError) as exc_info:
        await extract(archive_path=archive, dest_dir=tmp_path / "out")
    assert (
        exc_info.value.rejection_reason
        == RejectionReason.EXTRACT_BAD_ARCHIVE.value
    )


# ---------------------------------------------------------------------------
# Bomb defense (FR-004a)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bomb_detected_when_expansion_exceeds_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A high-compression-ratio archive whose uncompressed size
    exceeds the expansion cap is aborted with
    ``extract:bomb-detected`` and any partial output is cleaned
    up."""
    archive = tmp_path / "bomb.zip"
    # The body is mostly nulls so it compresses tiny but expands large.
    one_mb_zeros = b"\x00" * (1024 * 1024)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(20):
            zf.writestr(f"chunk-{i}.bin", one_mb_zeros)

    # Force the cap floor down so 20 MB triggers it (default floor
    # is 5 GiB which would never trigger for the test corpus).
    import importlib

    extract_mod = importlib.import_module("romarr.importer.steps.extract")
    monkeypatch.setattr(extract_mod, "_BOMB_FLOOR_BYTES", 1024 * 1024)
    # 4x compressed size (~few KB) plus the new 1 MB floor makes
    # ~ 1 MB cap. The 20 MB of actual content trips it.

    dest = tmp_path / "extracted"
    with pytest.raises(ExtractError) as exc_info:
        await extract(archive_path=archive, dest_dir=dest)
    assert (
        exc_info.value.rejection_reason
        == RejectionReason.EXTRACT_BOMB_DETECTED.value
    )
    # Partial files cleaned up.
    leftover = [p for p in dest.rglob("*") if p.is_file()]
    assert leftover == []


# ---------------------------------------------------------------------------
# Path-traversal defense (FR-004a)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zip_with_path_traversal_member_raises(tmp_path: Path) -> None:
    """A zip member like ``../../etc/passwd`` is rejected outright."""
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../etc/passwd", b"hijack")

    dest = tmp_path / "extracted"
    with pytest.raises(ExtractError) as exc_info:
        await extract(archive_path=archive, dest_dir=dest)
    assert (
        exc_info.value.rejection_reason
        == RejectionReason.EXTRACT_BAD_ARCHIVE.value
    )


# ---------------------------------------------------------------------------
# Unsupported format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_format_raises(tmp_path: Path) -> None:
    archive = tmp_path / "rom.tar"
    archive.write_bytes(b"some-tar-content")

    with pytest.raises(ExtractError) as exc_info:
        await extract(archive_path=archive, dest_dir=tmp_path / "out")
    assert (
        exc_info.value.rejection_reason
        == RejectionReason.EXTRACT_BAD_ARCHIVE.value
    )
