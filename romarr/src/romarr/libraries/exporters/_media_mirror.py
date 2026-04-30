"""Cover/asset mirroring for per-platform exporter directories.

ES-DE / Pegasus / LaunchBox all expect cover assets *under* the
library directory rather than referenced by absolute path. We
mirror the metadata-cache cover into
``<library>/<platform_slug>/media/covers/<slug>.<ext>``:

  * **Hardlink** when both files live on the same filesystem
    (constant-space, no copy cost).
  * **Copy with mtime preserved** otherwise — :func:`os.link`
    raises :exc:`OSError(errno.EXDEV)` across filesystems and we
    fall back to :func:`shutil.copy2`.

The helper is **idempotent**: re-running on the same input yields
the same on-disk state. When the source's mtime is newer than the
destination's, the destination is refreshed (FR-019).
"""

from __future__ import annotations

import errno
import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def materialise_cover(
    *,
    source: Path,
    dest_dir: Path,
    slug: str,
) -> str | None:
    """Mirror ``source`` (a cover file in the metadata cache) into
    ``dest_dir`` under the basename ``<slug>.<ext>``.

    ``source`` must already exist; the metadata-aggregation layer
    is responsible for materialising covers under ``data/covers/``.

    Returns the relative path to the destination file rooted at the
    *parent* of ``dest_dir`` (i.e., the gamelist.xml directory) —
    typically ``./media/covers/<slug>.<ext>`` (FR-018) — or
    ``None`` if ``source`` does not exist (FR-018a: the renderer
    omits the ``<image>`` element entirely).
    """
    if not source.exists():
        return None

    ext = source.suffix
    dest = dest_dir / f"{slug}{ext}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        # Refresh only when the source is strictly newer (idempotent
        # re-runs leave the mirror untouched).
        if source.stat().st_mtime <= dest.stat().st_mtime:
            return _relative_to_gamelist(dest_dir, ext, slug)
        dest.unlink()

    try:
        os.link(source, dest)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        # Cross-filesystem: copy with mtime preserved.
        shutil.copy2(source, dest)

    return _relative_to_gamelist(dest_dir, ext, slug)


def _relative_to_gamelist(dest_dir: Path, ext: str, slug: str) -> str:
    """gamelist.xml lives at ``<library>/<platform_slug>/gamelist.xml``;
    the cover lives at ``<library>/<platform_slug>/media/covers/...``.
    The XML's ``<image>`` element wants the relative path from the
    XML's directory: ``./media/covers/<slug>.<ext>``."""
    media_segment = dest_dir.name  # "covers"
    parent_segment = dest_dir.parent.name  # "media"
    return f"./{parent_segment}/{media_segment}/{slug}{ext}"


__all__ = ["materialise_cover"]
