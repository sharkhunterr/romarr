"""Cover-storage tests (T018 / FR-017, FR-017a)."""

from __future__ import annotations

from pathlib import Path

import pytest

from romarr.metadata.covers import (
    UnsupportedCoverContentTypeError,
    cover_path_for,
    derive_extension,
    write_cover,
)


def test_derive_extension_known_types() -> None:
    assert derive_extension("image/jpeg") == "jpg"
    assert derive_extension("image/png") == "png"
    assert derive_extension("image/webp") == "webp"
    # Strips parameters.
    assert derive_extension("image/jpeg; charset=binary") == "jpg"


def test_derive_extension_unknown_raises() -> None:
    with pytest.raises(UnsupportedCoverContentTypeError):
        derive_extension("image/gif")
    with pytest.raises(UnsupportedCoverContentTypeError):
        derive_extension("")


def test_write_cover_creates_file(metadata_env: Path) -> None:
    payload = b"fake-jpeg-bytes"
    path = write_cover(42, content_type="image/jpeg", data=payload)
    assert path == cover_path_for(42, "jpg")
    assert path.read_bytes() == payload


def test_write_cover_byte_equal_no_op(metadata_env: Path) -> None:
    payload = b"identical"
    path1 = write_cover(7, content_type="image/png", data=payload)
    mtime_before = path1.stat().st_mtime_ns
    # A second call with identical bytes must not rewrite the file.
    path2 = write_cover(7, content_type="image/png", data=payload)
    assert path1 == path2
    assert path2.stat().st_mtime_ns == mtime_before


def test_write_cover_content_type_change_unlinks_sibling(
    metadata_env: Path,
) -> None:
    """When the new cover is a different ext, the old file is removed
    (FR-017a: one-cover-per-Game invariant)."""
    write_cover(99, content_type="image/jpeg", data=b"jpeg-bytes")
    new_path = write_cover(99, content_type="image/png", data=b"png-bytes")

    assert new_path.exists()
    assert new_path == cover_path_for(99, "png")
    assert not cover_path_for(99, "jpg").exists()
