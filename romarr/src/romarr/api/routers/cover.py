"""Cover-art serving endpoint (slice 159).

Per spec 014 B.4 / J Romarr exposes covers via:

  * ``GET /api/v3/cover/{game_id}`` — streams the bytes stored
    under ``<data_dir>/covers/`` for the matching Game. Per
    the spec, the response carries ``Cache-Control:
    public, max-age=86400, immutable`` so a frontend that
    appends ``?v=<updated_at>`` for cache-busting gets long
    lived caching for free.

The :class:`Game` row carries an absolute filesystem path in
``cover_path`` (set by :mod:`romarr.metadata.refresh`); this
endpoint resolves the path, validates it lives inside the
configured covers directory (no path-traversal), and returns
the bytes via :class:`FileResponse`.

Read-only — any authenticated user can fetch covers; admin
isn't required because covers are public-friendly artwork
and locking them down would just complicate the
``<img src="">`` flow on every page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.auth import Principal
from romarr.config.settings import get_settings
from romarr.domain.models import Game

router = APIRouter(prefix="/api/v3/cover", tags=["Cover"])

# Per spec 014 J. Operator-controlled cache busting via a
# ``?v=<updated_at>`` query param keeps covers immutable for
# 24h once a render lands; bumping ``v`` forces a refetch.
_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=86400, immutable",
}


def _media_type_for(path: Path) -> str:
    """Lightweight content-type lookup so we don't pull in
    ``mimetypes`` just for three extensions."""
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "jpg" or suffix == "jpeg":
        return "image/jpeg"
    if suffix == "png":
        return "image/png"
    if suffix == "webp":
        return "image/webp"
    # Fall back to a generic image type — the file is in the
    # covers dir so it's by definition an image we wrote.
    return "application/octet-stream"


@router.get(
    "/{game_id}",
    response_class=FileResponse,
    summary=(
        "Stream the cover for a Game (any authenticated user). "
        "Cached for 24h with the ``immutable`` directive; the "
        "frontend cache-busts via ``?v=<updated_at>``."
    ),
)
async def get_cover(
    game_id: int,
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    row = (
        await db.execute(select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"game_id={game_id} not found",
                "errorCode": "game_not_found",
            },
        )

    cover_path_str = row.cover_path
    if cover_path_str is None or cover_path_str == "":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"game_id={game_id} has no cover stored",
                "errorCode": "no_cover",
            },
        )

    # Path-traversal guard: resolve and ensure the file lives
    # inside the configured covers directory. A stored
    # ``cover_path`` should always be inside that dir already
    # (write_cover puts it there) — this is belt-and-suspenders
    # for a hand-edited DB or future migrations.
    covers_root = (Path(get_settings().data_dir) / "covers").resolve()
    cover_path = Path(cover_path_str).resolve()
    try:
        cover_path.relative_to(covers_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": (
                    f"cover for game_id={game_id} is outside the "
                    "configured covers directory"
                ),
                "errorCode": "no_cover",
            },
        ) from None

    if not cover_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": (
                    f"cover file for game_id={game_id} not found on disk"
                ),
                "errorCode": "no_cover",
            },
        )

    return FileResponse(
        cover_path,
        media_type=_media_type_for(cover_path),
        headers=_CACHE_HEADERS,
    )


__all__ = ["router"]
