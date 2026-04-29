"""Cover-art persistence helpers (FR-017, FR-017a).

Covers live on the local filesystem under ``<data_dir>/covers/`` —
one cover per Game; the extension is derived from the response
Content-Type. A change in content-type replaces atomically (write the
new file first, delete any sibling with a different extension, update
:attr:`romarr.domain.models.Game.cover_path` in the same DB transaction
upstream).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from romarr.config.settings import get_settings

CoverExt = Literal["jpg", "png", "webp"]

KNOWN_COVER_EXTENSIONS: frozenset[CoverExt] = frozenset({"jpg", "png", "webp"})

_CONTENT_TYPE_MAP: dict[str, CoverExt] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/pjpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class UnsupportedCoverContentTypeError(ValueError):
    """Raised when a provider hands back a content-type we don't store."""


def derive_extension(content_type: str) -> CoverExt:
    """Pick a canonical extension from a HTTP ``Content-Type`` header.

    Strips parameters (``; charset=...``) and lower-cases. Raises
    :class:`UnsupportedCoverContentTypeError` for anything we don't
    natively persist (gif, bmp, avif, etc.).
    """
    if not content_type:
        raise UnsupportedCoverContentTypeError("empty content-type")
    primary = content_type.split(";", 1)[0].strip().lower()
    ext = _CONTENT_TYPE_MAP.get(primary)
    if ext is None:
        raise UnsupportedCoverContentTypeError(
            f"unsupported cover content-type: {primary!r}"
        )
    return ext


def _covers_dir() -> Path:
    return Path(get_settings().data_dir) / "covers"


def cover_path_for(game_id: int, ext: CoverExt) -> Path:
    """Return the absolute filesystem path for a Game's cover."""
    return _covers_dir() / f"{game_id}.{ext}"


def write_cover(
    game_id: int,
    *,
    content_type: str,
    data: bytes,
) -> Path:
    """Persist ``data`` as the cover for ``game_id``. Returns the path.

    Behaviour:
      - The covers dir is created on demand.
      - If a cover at the same extension already exists with byte-equal
        contents (SHA-256 match), the file is left untouched and the
        existing path is returned (no needless inode churn).
      - If a cover exists at a DIFFERENT extension (content-type
        change), the new file is written first, then the sibling at
        the old extension is unlinked. The caller is responsible for
        updating ``Game.cover_path`` in the same transaction upstream
        (FR-017a atomicity).
    """
    ext = derive_extension(content_type)
    target = cover_path_for(game_id, ext)
    target.parent.mkdir(parents=True, exist_ok=True)

    new_digest = hashlib.sha256(data).digest()
    if target.exists():
        existing_digest = hashlib.sha256(target.read_bytes()).digest()
        if existing_digest == new_digest:
            return target

    target.write_bytes(data)

    for sibling_ext in KNOWN_COVER_EXTENSIONS - {ext}:
        sibling = cover_path_for(game_id, sibling_ext)
        if sibling.exists():
            sibling.unlink()

    return target
