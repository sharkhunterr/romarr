"""Atomic move/hardlink tests (T060-T066, FR-024 / FR-025 / FR-026)."""

from __future__ import annotations

import errno
from collections.abc import Callable
from pathlib import Path

import pytest

from romarr.identification.hasher import Hasher
from romarr.importer.errors import MoveError
from romarr.importer.steps.move import MoveResult, move_atomic
from romarr.importer.types import RejectionReason


@pytest.fixture
def make_rom(tmp_path: Path) -> Callable[[bytes, str], tuple[Path, str]]:
    def _make(body: bytes = b"sonic-rom-bytes" * 1024, name: str = "rom.md") -> tuple[Path, str]:
        source = tmp_path / "downloads" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(body)
        sha1 = Hasher().hash_path(source).sha1
        return source, sha1

    return _make


# ---------------------------------------------------------------------------
# T060 — same-fs hardlink
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_fs_hardlink(
    tmp_path: Path,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom()
    dest = tmp_path / "library" / "Sonic.md"

    result = await move_atomic(source=source, dest=dest, expected_sha1=sha1)
    assert isinstance(result, MoveResult)
    assert result.used_hardlink is True
    assert result.coalesced is False
    assert result.bytes_copied == 0
    # Same fs ⇒ hardlink ⇒ same inode.
    assert source.stat().st_ino == dest.stat().st_ino


# ---------------------------------------------------------------------------
# T061 — cross-fs fallback to copy + verify + rename
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_fs_fallback_copy_verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom()
    dest = tmp_path / "library" / "Sonic.md"

    real_link = __import__("os").link

    def fake_link(src: object, dst: object, **_kwargs: object) -> None:
        # Simulate the EXDEV os.link raises across filesystems.
        raise OSError(errno.EXDEV, "Cross-device link", str(src))

    monkeypatch.setattr("romarr.importer.steps.move.os.link", fake_link)

    result = await move_atomic(source=source, dest=dest, expected_sha1=sha1)
    assert result.used_hardlink is False
    assert result.bytes_copied == source.stat().st_size
    # Different inode ⇒ copy, not link.
    assert source.stat().st_ino != dest.stat().st_ino
    # mtime preserved (copy2).
    assert source.stat().st_mtime == pytest.approx(dest.stat().st_mtime, abs=1)
    # No leftover .tmp.
    assert not (dest.with_name(dest.name + ".tmp")).exists()
    del real_link


# ---------------------------------------------------------------------------
# T062 — copy hash mismatch keeps source intact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_copy_hash_mismatch_keeps_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom()
    dest = tmp_path / "library" / "Sonic.md"

    monkeypatch.setattr(
        "romarr.importer.steps.move.os.link",
        lambda *_a, **_k: (_ for _ in ()).throw(
            OSError(errno.EXDEV, "Cross-device link")
        ),
    )

    # Force the cross-fs path AND inject a corrupted copy by
    # rewriting the file via shutil.copy2 monkeypatch.
    real_copy = __import__("shutil").copy2

    def corrupt_copy(src: object, dst: object, *args: object, **kwargs: object) -> str:
        ret = real_copy(src, dst, *args, **kwargs)
        Path(dst if isinstance(dst, (str, Path)) else "").write_bytes(b"corrupted")
        return ret  # type: ignore[return-value]

    monkeypatch.setattr("romarr.importer.steps.move.shutil.copy2", corrupt_copy)

    with pytest.raises(MoveError) as exc_info:
        await move_atomic(source=source, dest=dest, expected_sha1=sha1)
    assert exc_info.value.rejection_reason == RejectionReason.MOVE_HASH_MISMATCH.value
    # Source survives.
    assert source.exists()
    assert Hasher().hash_path(source).sha1 == sha1
    # No partial dest, no leftover .tmp.
    assert not dest.exists()
    assert not (dest.with_name(dest.name + ".tmp")).exists()


# ---------------------------------------------------------------------------
# T063 — destination already exists with matching SHA-1 (idempotent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_dest_matching_sha1_coalesces(
    tmp_path: Path,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom()
    # Pre-populate dest with the same body.
    dest = tmp_path / "library" / "Sonic.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(source.read_bytes())

    source_inode = source.stat().st_ino
    dest_inode_before = dest.stat().st_ino

    result = await move_atomic(source=source, dest=dest, expected_sha1=sha1)
    assert result.coalesced is True
    assert result.used_hardlink is False
    # Both files survive untouched.
    assert source.stat().st_ino == source_inode
    assert dest.stat().st_ino == dest_inode_before


# ---------------------------------------------------------------------------
# T064 — destination exists with mismatching SHA-1 + force=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_dest_mismatching_sha1_no_force_raises(
    tmp_path: Path,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom()
    dest = tmp_path / "library" / "Sonic.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"different-bytes-entirely")

    with pytest.raises(MoveError) as exc_info:
        await move_atomic(source=source, dest=dest, expected_sha1=sha1)
    assert (
        exc_info.value.rejection_reason
        == RejectionReason.DESTINATION_COLLISION.value
    )
    # Both files preserved.
    assert dest.read_bytes() == b"different-bytes-entirely"
    assert source.exists()


@pytest.mark.asyncio
async def test_existing_dest_mismatching_sha1_with_force_overwrites(
    tmp_path: Path,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom(body=b"new-content" * 256, name="new.md")
    dest = tmp_path / "library" / "Sonic.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"stale-bytes")

    result = await move_atomic(
        source=source, dest=dest, expected_sha1=sha1, force=True
    )
    # Force-overwrites either via hardlink (same fs) or copy.
    assert result.coalesced is False
    assert dest.exists()
    assert Hasher().hash_path(dest).sha1 == sha1


# ---------------------------------------------------------------------------
# T065 — fault injection: copy2 raises mid-write ⇒ no partial dest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crash_mid_copy_no_partial_dest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom()
    dest = tmp_path / "library" / "Sonic.md"

    monkeypatch.setattr(
        "romarr.importer.steps.move.os.link",
        lambda *_a, **_k: (_ for _ in ()).throw(
            OSError(errno.EXDEV, "Cross-device link")
        ),
    )

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.EIO, "simulated I/O error")

    monkeypatch.setattr("romarr.importer.steps.move.shutil.copy2", boom)

    with pytest.raises(MoveError):
        await move_atomic(source=source, dest=dest, expected_sha1=sha1)

    assert not dest.exists()
    assert not (dest.with_name(dest.name + ".tmp")).exists()
    assert source.exists()


# ---------------------------------------------------------------------------
# T066 — disk full preserves source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disk_full_preserves_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom()
    dest = tmp_path / "library" / "Sonic.md"

    monkeypatch.setattr(
        "romarr.importer.steps.move.os.link",
        lambda *_a, **_k: (_ for _ in ()).throw(
            OSError(errno.ENOSPC, "No space left on device")
        ),
    )

    with pytest.raises(MoveError) as exc_info:
        await move_atomic(source=source, dest=dest, expected_sha1=sha1)
    assert exc_info.value.rejection_reason == RejectionReason.MOVE_DISK_FULL.value
    assert source.exists()
    assert not dest.exists()


# ---------------------------------------------------------------------------
# Permission errors map to the right RejectionReason
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_denied_maps_to_permission_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_rom: Callable[..., tuple[Path, str]],
) -> None:
    source, sha1 = make_rom()
    dest = tmp_path / "library" / "Sonic.md"

    monkeypatch.setattr(
        "romarr.importer.steps.move.os.link",
        lambda *_a, **_k: (_ for _ in ()).throw(
            OSError(errno.EACCES, "Permission denied")
        ),
    )

    with pytest.raises(MoveError) as exc_info:
        await move_atomic(source=source, dest=dest, expected_sha1=sha1)
    assert (
        exc_info.value.rejection_reason
        == RejectionReason.MOVE_PERMISSION_ERROR.value
    )
