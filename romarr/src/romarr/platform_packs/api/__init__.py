"""FastAPI routers for the platform-packs feature.

Two routers, both admin-gated:

  - :mod:`romarr.platform_packs.api.packs` mounts the pack-lifecycle
    endpoints (upload, list, detail, re-apply, validate-only) under
    ``/api/v3/rom/platform-pack``.
  - :mod:`romarr.platform_packs.api.platforms` mounts the override +
    format-CRUD endpoints under ``/api/v3/rom/platform``.
"""

from romarr.platform_packs.api.packs import router as packs_router
from romarr.platform_packs.api.platforms import router as platforms_router
from romarr.platform_packs.api.sources import router as sources_router

__all__ = [
    "packs_router",
    "platforms_router",
    "sources_router",
]
