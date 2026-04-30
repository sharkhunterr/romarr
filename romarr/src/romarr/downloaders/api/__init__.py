"""FastAPI routers for the download-clients feature.

Two routers, both admin-gated (CL005 / FR-026a):

  - :mod:`romarr.downloaders.api.clients` — CRUD + /test
  - :mod:`romarr.downloaders.api.schema`  — implementation discovery

Mounted in :func:`romarr.api.app.create_app` under
``/api/v3/downloadclient*``.
"""

from romarr.downloaders.api.clients import router as clients_router
from romarr.downloaders.api.schema import router as schema_router

__all__ = ["clients_router", "schema_router"]
