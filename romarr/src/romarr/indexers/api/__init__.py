"""FastAPI routers for the indexer feature.

Three routers, all admin-gated:

  - :mod:`romarr.indexers.api.applications` — Prowlarr registration
  - :mod:`romarr.indexers.api.indexers`     — indexer CRUD + /test
  - :mod:`romarr.indexers.api.tests`        — connectivity probe alone

Mounted in ``romarr.api.app.create_app`` under ``/api/v3/applications``
and ``/api/v3/indexer*``.
"""

from romarr.indexers.api.applications import router as applications_router
from romarr.indexers.api.grabarr import router as grabarr_wizard_router
from romarr.indexers.api.indexers import router as indexers_router

__all__ = [
    "applications_router",
    "grabarr_wizard_router",
    "indexers_router",
]
