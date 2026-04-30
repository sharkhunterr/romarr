"""Cover-asset mirror tests (T055, T056, T057, FR-018, FR-018a)."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from romarr.libraries.exporters._media_mirror import materialise_cover


def _png(path: Path, body: bytes = b"png-bytes") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


# ---------------------------------------------------------------------------
# T055 — same-fs hardlink path
# ---------------------------------------------------------------------------


def test_hardlink_when_same_fs(tmp_path: Path) -> None:
    source = _png(tmp_path / "data" / "covers" / "sonic.png")
    dest_dir = tmp_path / "library" / "megadrive" / "media" / "covers"

    rel = materialise_cover(source=source, dest_dir=dest_dir, slug="sonic")
    assert rel == "./media/covers/sonic.png"

    dest = dest_dir / "sonic.png"
    assert dest.exists()
    # Same fs ⇒ hardlink ⇒ same inode.
    assert source.stat().st_ino == dest.stat().st_ino


# ---------------------------------------------------------------------------
# T056 — cross-fs fallback to copy2
# ---------------------------------------------------------------------------


def test_copy_fallback_cross_fs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _png(tmp_path / "data" / "covers" / "sonic.png")
    dest_dir = tmp_path / "library" / "megadrive" / "media" / "covers"

    real_link = os.link

    def fake_link(src: object, dst: object, **_kwargs: object) -> None:
        # Simulate the EXDEV that os.link raises across filesystems.
        raise OSError(errno.EXDEV, "Cross-device link", str(src))

    monkeypatch.setattr(
        "romarr.libraries.exporters._media_mirror.os.link", fake_link
    )

    rel = materialise_cover(source=source, dest_dir=dest_dir, slug="sonic")
    assert rel == "./media/covers/sonic.png"
    dest = dest_dir / "sonic.png"
    assert dest.exists()
    # Different inode: it was copied, not linked.
    assert source.stat().st_ino != dest.stat().st_ino
    # mtime preserved (copy2).
    assert source.stat().st_mtime == pytest.approx(dest.stat().st_mtime, abs=1)
    del real_link  # silence unused


# ---------------------------------------------------------------------------
# T057 — refresh on metadata update
# ---------------------------------------------------------------------------


def test_refresh_on_metadata_update(tmp_path: Path) -> None:
    source = _png(tmp_path / "data" / "covers" / "sonic.png", body=b"v1")
    dest_dir = tmp_path / "library" / "megadrive" / "media" / "covers"

    materialise_cover(source=source, dest_dir=dest_dir, slug="sonic")
    dest = dest_dir / "sonic.png"
    assert dest.read_bytes() == b"v1"

    # Update the source with a fresh mtime.
    source.write_bytes(b"v2-fresh")
    new_mtime = source.stat().st_mtime + 5
    os.utime(source, (new_mtime, new_mtime))

    materialise_cover(source=source, dest_dir=dest_dir, slug="sonic")
    assert dest.read_bytes() == b"v2-fresh"


def test_no_refresh_when_source_unchanged(tmp_path: Path) -> None:
    source = _png(tmp_path / "data" / "covers" / "sonic.png", body=b"v1")
    dest_dir = tmp_path / "library" / "megadrive" / "media" / "covers"

    materialise_cover(source=source, dest_dir=dest_dir, slug="sonic")
    dest = dest_dir / "sonic.png"
    inode_before = dest.stat().st_ino

    # Re-run with no source change.
    materialise_cover(source=source, dest_dir=dest_dir, slug="sonic")
    inode_after = dest.stat().st_ino
    # Same inode ⇒ no relink, no copy.
    assert inode_before == inode_after


# ---------------------------------------------------------------------------
# FR-018a — missing source returns None (renderer omits <image>)
# ---------------------------------------------------------------------------


def test_missing_source_returns_none(tmp_path: Path) -> None:
    source = tmp_path / "data" / "covers" / "missing.png"
    dest_dir = tmp_path / "library" / "megadrive" / "media" / "covers"
    rel = materialise_cover(source=source, dest_dir=dest_dir, slug="missing")
    assert rel is None
    assert not (dest_dir / "missing.png").exists()
