"""Sonarr-shape `/api/v3/system/log*` endpoints (T054, FR-014).

Three routes mirror Sonarr's logs surface:

  * **GET ``/api/v3/system/log``** — paginated structured log
    entries. MVP returns an empty canonical pagination envelope
    so the frontend can wire against the contract; the entries
    will materialise once Romarr's structlog → JSON-line file
    sink is configured (tracked separately).
  * **GET ``/api/v3/system/log/file``** — list of log files
    that exist in :attr:`Settings.log_dir`. Each entry carries
    the filename, byte size, and last-modified timestamp.
    Returns ``[]`` when the directory is empty or absent (the
    operator may not have configured file logging yet).
  * **GET ``/api/v3/system/log/file/{filename}``** — stream the
    named file as ``text/plain``. Filename is sanitised to
    prevent path traversal; admin-only.

Read-list endpoints are gated by :func:`require_readonly`.
File download is :func:`require_admin` because logs commonly
contain sensitive operational data (URLs with API keys, error
stack traces with paths).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from romarr.api.dependencies import require_admin, require_readonly
from romarr.api.envelopes import PaginationEnvelope
from romarr.api.log_capture import LOG_BUFFER
from romarr.api.pagination import PageRequest, page_request
from romarr.auth import Principal
from romarr.config import get_settings

router = APIRouter(prefix="/api/v3/system/log", tags=["Log"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LogEntry(BaseModel):
    """One structured log entry — Sonarr-shape camelCase JSON."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    time: datetime
    level: str  # 'debug' | 'info' | 'warn' | 'error' | 'fatal'
    logger: str
    message: str
    exception: str | None = None
    exception_type: str | None = Field(
        alias="exceptionType", default=None
    )


class LogFileEntry(BaseModel):
    """One log file's metadata."""

    model_config = ConfigDict(populate_by_name=True)

    filename: str
    last_write_time: datetime = Field(alias="lastWriteTime")
    contents_size: int = Field(alias="contentsSize")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_log_dir() -> Path:
    return Path(get_settings().log_dir).resolve()


def _safe_log_path(filename: str) -> Path:
    """Resolve ``filename`` against the log dir while rejecting
    path-traversal. Raises HTTPException(400) on bad input."""
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "filename must be a plain log file name",
                "errorCode": "invalid_log_filename",
            },
        )
    log_dir = _resolve_log_dir()
    candidate = (log_dir / filename).resolve()
    # Path-traversal guard: the resolved path MUST live under
    # log_dir. The string-based check above is a fast reject;
    # this is the canonical filesystem check.
    if not candidate.is_relative_to(log_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "filename escapes log directory",
                "errorCode": "invalid_log_filename",
            },
        )
    return candidate


# ---------------------------------------------------------------------------
# GET /api/v3/system/log — paginated entries (MVP stub)
# ---------------------------------------------------------------------------


# Slice 391 — minimum-level filter mapping. Operator-friendly
# vocabulary; backend stores numeric ``logging`` level.
_LEVEL_NAME_TO_NO: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
    "critical": logging.CRITICAL,
}


@router.get(
    "",
    response_model=PaginationEnvelope[LogEntry],
    response_model_by_alias=True,
    summary=(
        "Paginated structured log entries pulled from the in-process "
        "ring buffer. Newest first. Optional ``level`` (minimum level "
        "to keep) and ``logger`` (case-insensitive substring) filters."
    ),
)
async def list_log_entries(
    _principal: Annotated[Principal, Depends(require_readonly)],
    page_req: Annotated[PageRequest, Depends(page_request)],
    level: Annotated[
        str | None,
        Query(
            description=(
                "Minimum level to keep — debug / info / warn / "
                "error / fatal. Default: include everything."
            ),
        ),
    ] = None,
    logger: Annotated[
        str | None,
        Query(
            description=(
                "Case-insensitive substring match on the logger "
                "name (e.g. ``importer`` to scope the view to "
                "every ``romarr.importer.*`` line)."
            ),
        ),
    ] = None,
) -> PaginationEnvelope[LogEntry]:
    """Slice 391 — surface the in-memory ring buffer.

    The handler installed by :func:`romarr.api.log_capture.install`
    keeps the most recent ~2000 records. We project each into the
    Sonarr-shape :class:`LogEntry` so the frontend Logs page can
    render without contract churn.
    """
    min_level: int | None = None
    if level is not None:
        min_level = _LEVEL_NAME_TO_NO.get(level.lower())
        if min_level is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "errorMessage": (
                        f"unknown level={level!r} — expected one of "
                        f"{sorted(set(_LEVEL_NAME_TO_NO))}"
                    ),
                    "errorCode": "invalid_log_level",
                },
            )

    offset = (page_req.page - 1) * page_req.page_size
    records, total = LOG_BUFFER.snapshot(
        limit=page_req.page_size,
        offset=offset,
        min_level=min_level,
        logger_substring=logger,
    )

    entries = [
        LogEntry(
            id=r["id"],
            time=datetime.fromisoformat(r["timestamp"]),
            level=_level_to_sonarr(r["level_no"]),
            logger=r["logger"],
            message=r["message"],
            exception=r["exception_text"],
            exceptionType=(
                r["exception_text"].splitlines()[-1].split(":", 1)[0]
                if r["exception_text"]
                else None
            ),
        )
        for r in records
    ]

    return PaginationEnvelope[LogEntry](
        page=page_req.page,
        page_size=page_req.page_size,
        sort_key=page_req.sort_key or "time",
        sort_direction=page_req.sort_direction,
        total_records=total,
        records=entries,
    )


def _level_to_sonarr(level_no: int) -> str:
    """Project numeric :mod:`logging` level → Sonarr vocabulary."""
    if level_no >= logging.CRITICAL:
        return "fatal"
    if level_no >= logging.ERROR:
        return "error"
    if level_no >= logging.WARNING:
        return "warn"
    if level_no >= logging.INFO:
        return "info"
    return "debug"


# ---------------------------------------------------------------------------
# GET /api/v3/system/log/file — list log files
# ---------------------------------------------------------------------------


@router.get(
    "/file",
    response_model=list[LogFileEntry],
    response_model_by_alias=True,
    summary=(
        "List every log file under ``Settings.log_dir`` with its "
        "size and last-modified timestamp. Returns [] when the "
        "directory is empty or absent."
    ),
)
async def list_log_files(
    _principal: Annotated[Principal, Depends(require_readonly)],
) -> list[LogFileEntry]:
    log_dir = _resolve_log_dir()
    if not log_dir.is_dir():
        return []

    entries: list[LogFileEntry] = []
    for path in log_dir.iterdir():
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append(
            LogFileEntry(
                filename=path.name,
                last_write_time=datetime.fromtimestamp(
                    stat.st_mtime, tz=UTC
                ),
                contents_size=stat.st_size,
            )
        )
    # Most recent first — matches Sonarr's UI ordering.
    entries.sort(key=lambda e: e.last_write_time, reverse=True)
    return entries


# ---------------------------------------------------------------------------
# GET /api/v3/system/log/file/{filename} — stream a log file
# ---------------------------------------------------------------------------


@router.get(
    "/file/{filename}",
    response_class=FileResponse,
    summary=(
        "Stream a log file as text/plain. Admin-only — log "
        "contents commonly include URLs with API keys and stack "
        "traces with on-disk paths."
    ),
)
async def download_log_file(
    filename: str,
    _admin: Annotated[Principal, Depends(require_admin)],
) -> FileResponse:
    path = _safe_log_path(filename)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"log file {filename!r} not found",
                "errorCode": "not_found",
            },
        )
    return FileResponse(
        path,
        media_type="text/plain",
        filename=filename,
    )


__all__ = ["router"]
