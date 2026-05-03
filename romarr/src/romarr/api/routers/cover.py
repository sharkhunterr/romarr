"""Cover-art surface (slices 159, 160).

Per spec 014 B.4 / J Romarr exposes covers via:

  * ``GET    /api/v3/cover/{game_id}`` — streams the bytes
    stored under ``<data_dir>/covers/`` for the matching Game.
    ``Cache-Control: public, max-age=86400, immutable``;
    operators cache-bust by appending ``?v=<updated_at>``.
  * ``PUT    /api/v3/cover/{game_id}`` — operator override:
    fetch the URL bytes, persist via
    :func:`romarr.metadata.covers.write_cover`, update
    ``Game.cover_path``, optionally auto-lock the ``cover``
    field so the spec-002 aggregator stops trying to overwrite
    the operator's pick (admin only).
  * ``DELETE /api/v3/cover/{game_id}`` — clear the cover
    (remove file + null the path; admin only).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.config.settings import get_settings
from romarr.domain.models import Game
from romarr.domain.schemas import GameRead
from romarr.metadata.covers import (
    UnsupportedCoverContentTypeError,
    derive_extension,
    write_cover,
)

router = APIRouter(prefix="/api/v3/cover", tags=["Cover"])

# Defensive limits for the operator URL-paste path. 20 MB is
# generous for cover art (a typical SteamGridDB grid is well
# under 1 MB); 30 s timeout matches the network-call ceiling
# we use on other operator-driven HTTP fan-outs.
_MAX_FETCH_BYTES = 20 * 1024 * 1024
_FETCH_TIMEOUT_S = 30.0

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


class CoverOverrideRequest(BaseModel):
    """PUT /api/v3/cover/{game_id} — slice 160.

    Operator override for the auto-fetched cover. The supplied
    URL is fetched server-side (so the browser's CORS / mixed-
    content rules don't matter) and persisted via the same
    :func:`write_cover` pipeline the metadata aggregator uses.

    ``auto_lock`` defaults to True so the operator's pick
    survives the next refresh — the same anti-RomM-#1770
    pattern that slice 147 ships for text fields.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    url: HttpUrl
    auto_lock: bool = True


@router.put(
    "/{game_id}",
    response_model=GameRead,
    response_model_by_alias=False,
    status_code=status.HTTP_200_OK,
    summary=(
        "Override the cover for a Game by fetching bytes from "
        "an operator-supplied URL (admin only). Optionally "
        "auto-locks the cover field so the metadata aggregator "
        "stops overwriting it."
    ),
)
async def put_cover(
    game_id: int,
    body: Annotated[CoverOverrideRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameRead:
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

    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT_S,
            follow_redirects=True,
        ) as client:
            response = await client.get(str(body.url))
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "errorMessage": f"could not fetch cover URL: {exc}",
                "errorCode": "cover_fetch_failed",
            },
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "errorMessage": (
                    f"cover URL returned {response.status_code}"
                ),
                "errorCode": "cover_fetch_failed",
            },
        )

    if len(response.content) > _MAX_FETCH_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": (
                    f"cover exceeds {_MAX_FETCH_BYTES // (1024 * 1024)} "
                    "MB cap"
                ),
                "errorCode": "cover_too_large",
            },
        )

    content_type = response.headers.get("content-type", "")
    try:
        derive_extension(content_type)
    except UnsupportedCoverContentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": str(exc),
                "errorCode": "unsupported_content_type",
            },
        ) from exc

    path = write_cover(
        game_id, content_type=content_type, data=response.content
    )
    row.cover_path = str(path)
    if body.auto_lock:
        # Lock the COVER field so the aggregator skips it on
        # the next refresh. Identical to the slice 146 pattern.
        current = set(row.locked_fields or [])
        current.add("cover")
        row.locked_fields = sorted(current)

    await db.commit()
    await db.refresh(row)
    return GameRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{game_id}",
    response_model=GameRead,
    response_model_by_alias=False,
    summary=(
        "Clear the cover for a Game — removes the on-disk file "
        "and nulls ``cover_path`` (admin only). The aggregator "
        "will refetch on the next refresh unless ``cover`` is "
        "locked."
    ),
)
async def delete_cover(
    game_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameRead:
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
    if cover_path_str:
        # Same path-traversal guard as the GET — don't let a
        # bad row trick us into unlinking an arbitrary file.
        covers_root = (
            Path(get_settings().data_dir) / "covers"
        ).resolve()
        cover_path = Path(cover_path_str).resolve()
        try:
            cover_path.relative_to(covers_root)
        except ValueError:
            cover_path = None  # Don't unlink; just clear the row.
        if cover_path is not None and cover_path.is_file():
            cover_path.unlink()
    row.cover_path = None

    await db.commit()
    await db.refresh(row)
    return GameRead.model_validate(row, from_attributes=True)


__all__ = ["router"]
