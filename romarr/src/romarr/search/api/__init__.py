"""FastAPI routers for the search subsystem.

Five admin-gated routers (FR-026):

  - :mod:`romarr.search.api.search`    — /api/v3/rom/search/*
  - :mod:`romarr.search.api.grab`      — /api/v3/rom/release/grab
  - :mod:`romarr.search.api.command`   — /api/v3/command (Sonarr-compat)
  - :mod:`romarr.search.api.history`   — /api/v3/rom/search/history
  - :mod:`romarr.search.api.blocklist` — /api/v3/blocklist*

Mounted in :func:`romarr.api.app.create_app`.
"""

from romarr.search.api.blocklist import router as blocklist_router
from romarr.search.api.command import router as command_router
from romarr.search.api.grab import router as grab_router
from romarr.search.api.history import router as history_router
from romarr.search.api.search import router as search_router

__all__ = [
    "blocklist_router",
    "command_router",
    "grab_router",
    "history_router",
    "search_router",
]
