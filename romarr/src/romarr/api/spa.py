"""SPA (Single-Page Application) static-file mount.

Serves the built React frontend from ``Settings.spa_dist_path``
when ``Settings.spa_enabled`` is True. Mounted at ``/`` AFTER
every router so router routes still take precedence; only
unmatched paths fall through to ``index.html`` (which lets
React Router handle the URL on the client side).

The constitution mandates a single Docker image with the
frontend bundled — this module is what makes that real. In
test environments the flag stays False; the FastAPI app
preserves its existing JSON ``GET /`` smoke response so the
auth-endpoint tests don't break.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

if TYPE_CHECKING:
    from fastapi import FastAPI

_logger = logging.getLogger(__name__)


def register_spa(
    app: "FastAPI",
    *,
    enabled: bool,
    dist_path: str,
) -> bool:
    """Mount the SPA at ``/`` if enabled and the dist exists.

    Returns ``True`` when the mount was registered, ``False``
    otherwise. The boolean lets the caller decide whether to
    keep its fallback ``GET /`` JSON handler.
    """
    if not enabled:
        return False

    dist_root = Path(dist_path).resolve()
    index_html = dist_root / "index.html"
    if not index_html.is_file():
        _logger.warning(
            "spa.mount_skipped_missing_dist",
            extra={"dist_path": str(dist_root)},
        )
        return False

    # Mount /assets first (Vite emits hashed JS/CSS here).
    assets_dir = dist_root / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="spa-assets",
        )

    # Top-level static files Vite emits (manifest, service
    # worker, icons, favicon). Each is wired explicitly so the
    # router-level path matching stays predictable; a wildcard
    # static mount at ``/`` would shadow API routes.
    _STATIC_FILES = (
        "manifest.webmanifest",
        "registerSW.js",
        "sw.js",
        "favicon.ico",
        "robots.txt",
        "icon-192.png",
        "icon-512.png",
        "icon-512-maskable.png",
        "apple-touch-icon.png",
    )
    for name in _STATIC_FILES:
        path = dist_root / name
        if path.is_file():
            _register_file(app, name, path)

    # Catch-all: any unmatched non-API path returns
    # ``index.html`` so the client-side router (React Router)
    # can resolve the URL. Registered LAST so router routes
    # win.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> FileResponse:
        # Defence: don't shadow the API surface even when the
        # specific path matchers above missed (e.g. /api/...
        # for an unknown router). FastAPI / Starlette's
        # internal route-matching runs registered routes
        # first, so this handler only fires for paths that
        # didn't match anything else, but we still want a
        # 404 for anything that tried to reach an API path.
        if full_path.startswith("api/") or full_path.startswith("signalr/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(index_html)

    _logger.info(
        "spa.mounted",
        extra={"dist_path": str(dist_root)},
    )
    return True


def _register_file(app: "FastAPI", name: str, path: Path) -> None:
    """Register an explicit ``GET /{name}`` returning the file."""

    async def _serve() -> FileResponse:
        return FileResponse(path)

    app.add_api_route(
        f"/{name}",
        _serve,
        methods=["GET"],
        include_in_schema=False,
    )


__all__ = ["register_spa"]
