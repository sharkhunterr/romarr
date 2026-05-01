"""FastAPI routers for the search subsystem.

Four admin-gated routers (FR-026):

  - :mod:`romarr.search.api.search`    — /api/v3/rom/search/*
  - :mod:`romarr.search.api.grab`      — /api/v3/rom/release/grab
  - :mod:`romarr.search.api.history`   — /api/v3/rom/search/history
  - :mod:`romarr.search.api.blocklist` — /api/v3/blocklist*

The Sonarr-compat ``/api/v3/command`` endpoint moved to spec
012's ``romarr.tasks.api.command_router`` — that's the
canonical owner per FR-016 of spec 012, and it dispatches
through the scheduler so all jobs (not just the search
rounds) are reachable. The legacy router under
``romarr.search.api.command`` was removed in slice 17.

Mounted in :func:`romarr.api.app.create_app`.
"""

from romarr.search.api.blocklist import router as blocklist_router
from romarr.search.api.grab import router as grab_router
from romarr.search.api.history import router as history_router
from romarr.search.api.search import router as search_router

__all__ = [
    "blocklist_router",
    "grab_router",
    "history_router",
    "search_router",
]
