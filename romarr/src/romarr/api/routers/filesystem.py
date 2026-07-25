"""``/api/v3/system/filesystem`` — server-side directory browser.

Powers the path-picker on Settings > Media Management (create /
edit library). Two shapes served by a single endpoint keyed by
``path`` :

  * **``path`` omitted or ``/``** — returns a curated set of
    likely-interesting top-level directories (``/data``,
    ``/downloads``, ``/roms``, ``/media``, ``/mnt``, ``/config``,
    ``/srv``, ``/opt``, ``/home``). Anything the operator
    ``-v`` mounted usually shows up.
  * **``path=/some/dir``** — returns the direct children of that
    directory (subdirectories only, hidden entries filtered out).

Admin-gated : browsing the container's filesystem is admin-only
even though it never returns file contents — the topology alone
is sensitive.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from romarr.api.dependencies import require_admin
from romarr.auth import Principal

router = APIRouter(prefix="/api/v3/system/filesystem", tags=["System"])


# Hard block on paths that reveal kernel / init internals with no
# operator use case. Path can't be under any of these prefixes.
_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/etc",
    "/root",
    "/run",
    "/tmp",
    "/var/log",
    "/var/lib/docker",
)

# Top-level directories the root listing surfaces when present.
# Any of these that don't exist on the container are just skipped.
_LIKELY_MOUNTS: tuple[str, ...] = (
    "/data",
    "/downloads",
    "/roms",
    "/media",
    "/mnt",
    "/config",
    "/srv",
    "/opt",
    "/home",
    "/app",
    "/library",
    "/games",
)


class Entry(BaseModel):
    """One directory in a listing."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    path: str
    """Absolute path — pass back verbatim as ``?path=`` to descend."""
    is_dir: bool = True
    """Always True for the current implementation; kept explicit so a
    future file-mode extension doesn't break existing clients."""
    is_mount: bool = False
    """True when this entry sits on a different filesystem than its
    parent — a hint that this is one of the ``-v`` volumes the
    operator wanted to expose."""


class ListingResponse(BaseModel):
    """One directory listing."""

    path: str
    """The absolute path that was listed."""
    parent: str | None
    """Absolute path of the parent, or ``None`` when ``path == '/'``."""
    entries: list[Entry]


def _is_forbidden(resolved: Path) -> bool:
    s = str(resolved)
    return any(
        s == prefix or s.startswith(prefix + "/") for prefix in _FORBIDDEN_PREFIXES
    )


def _entry_from_path(path: Path, parent_dev: int | None = None) -> Entry:
    """Build one :class:`Entry` from a filesystem path.

    ``parent_dev``, when provided, lets the listing flag entries
    that live on a different filesystem — a strong indicator that
    the operator mounted a Docker volume here.
    """
    try:
        st = path.stat()
        is_mount = parent_dev is not None and st.st_dev != parent_dev
    except OSError:
        is_mount = False
    return Entry(
        name=path.name or str(path),
        path=str(path),
        is_dir=True,
        is_mount=is_mount,
    )


@router.get(
    "",
    response_model=ListingResponse,
    summary="List subdirectories of a path (admin).",
)
async def list_directory(
    _admin: Annotated[Principal, Depends(require_admin)],
    path: Annotated[str, Query()] = "/",
) -> ListingResponse:
    # Empty query defaults to the root listing.
    raw = path.strip() or "/"
    try:
        target = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": f"invalid path: {e}",
                "errorCode": "invalid_path",
            },
        ) from e

    if _is_forbidden(target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "errorMessage": f"path {str(target)!r} is not browsable",
                "errorCode": "path_forbidden",
            },
        )

    # Curated root — filter _LIKELY_MOUNTS down to the ones that exist.
    if str(target) == "/":
        entries: list[Entry] = []
        for candidate in _LIKELY_MOUNTS:
            p = Path(candidate)
            if p.is_dir():
                entries.append(_entry_from_path(p))
        return ListingResponse(
            path="/",
            parent=None,
            entries=entries,
        )

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": f"path {str(target)!r} not found",
                "errorCode": "not_found",
            },
        )
    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": f"path {str(target)!r} is not a directory",
                "errorCode": "not_a_directory",
            },
        )

    try:
        parent_dev: int | None = target.stat().st_dev
    except OSError:
        parent_dev = None

    entries = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue  # hide dotfiles
            try:
                if not child.is_dir():
                    continue
            except OSError:
                continue  # broken symlink — skip
            if _is_forbidden(child.resolve()):
                continue
            entries.append(_entry_from_path(child, parent_dev=parent_dev))
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "errorMessage": f"permission denied on {str(target)!r}",
                "errorCode": "permission_denied",
            },
        ) from e
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "errorMessage": f"failed to list {str(target)!r}: {e}",
                "errorCode": "listing_failed",
            },
        ) from e

    parent = str(target.parent) if target != Path("/") else None
    return ListingResponse(
        path=str(target),
        parent=parent,
        entries=entries,
    )


__all__ = ["router"]
