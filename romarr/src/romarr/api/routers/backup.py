"""Sonarr-shape `/api/v3/system/backup*` endpoints (T055, FR-014).

Two routes mirror Sonarr's backup management surface:

  * **GET ``/api/v3/system/backup``** — list backup files in
    :attr:`Settings.backup_path` with filename / size /
    last-modified timestamp. Returns ``[]`` when the directory
    is empty or absent. Read-only via :func:`require_readonly`.
  * **DELETE ``/api/v3/system/backup/{filename}``** — remove a
    backup file. Admin-only; rejects path-traversal attempts
    and dotfile-prefixed names defense-in-depth.

The "trigger a backup now" flow is already served by the
unified command bus: ``POST /api/v3/command {"name": "Backup"}``
runs the spec 012 BackupRunner. No dedicated endpoint here —
keeping a single trigger surface avoids two-implementations
drift.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from romarr.api.dependencies import require_admin, require_readonly
from romarr.auth import Principal
from romarr.config import get_settings

router = APIRouter(prefix="/api/v3/system/backup", tags=["Backup"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BackupFileEntry(BaseModel):
    """One backup file's metadata."""

    model_config = ConfigDict(populate_by_name=True)

    filename: str
    last_write_time: datetime = Field(alias="lastWriteTime")
    size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_backup_path() -> Path:
    return Path(get_settings().backup_path).resolve()


def _safe_backup_path(filename: str) -> Path:
    """Resolve ``filename`` against the backup dir while
    rejecting path-traversal. Mirrors the log router's guard —
    string-based fast reject, then the canonical
    ``is_relative_to`` check against the resolved dir."""
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "filename must be a plain backup file name",
                "errorCode": "invalid_backup_filename",
            },
        )
    backup_dir = _resolve_backup_path()
    candidate = (backup_dir / filename).resolve()
    if not candidate.is_relative_to(backup_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "filename escapes backup directory",
                "errorCode": "invalid_backup_filename",
            },
        )
    return candidate


# ---------------------------------------------------------------------------
# GET /api/v3/system/backup — list backups
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[BackupFileEntry],
    response_model_by_alias=True,
    summary=(
        "List every backup file under ``Settings.backup_path``. "
        "Each entry carries filename / lastWriteTime / size. "
        "Returns [] when the directory is empty or absent."
    ),
)
async def list_backups(
    _principal: Annotated[Principal, Depends(require_readonly)],
) -> list[BackupFileEntry]:
    backup_dir = _resolve_backup_path()
    if not backup_dir.is_dir():
        return []

    entries: list[BackupFileEntry] = []
    for path in backup_dir.iterdir():
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append(
            BackupFileEntry(
                filename=path.name,
                last_write_time=datetime.fromtimestamp(
                    stat.st_mtime, tz=UTC
                ),
                size=stat.st_size,
            )
        )
    # Newest first — the operator UI wants the latest backup at the top.
    entries.sort(key=lambda e: e.last_write_time, reverse=True)
    return entries


# ---------------------------------------------------------------------------
# DELETE /api/v3/system/backup/{filename} — remove a backup
# ---------------------------------------------------------------------------


@router.delete(
    "/{filename}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=(
        "Delete a backup file. Admin-only. The destructive "
        "Article XII confirmation flow lives in the operator "
        "UI; the API itself just removes the file when called."
    ),
)
async def delete_backup(
    filename: str,
    _admin: Annotated[Principal, Depends(require_admin)],
) -> None:
    path = _safe_backup_path(filename)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"backup file {filename!r} not found",
                "errorCode": "not_found",
            },
        )
    path.unlink()


__all__ = ["router"]
