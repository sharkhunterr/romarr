"""FastAPI routers for the metadata aggregation layer.

Three routers, all admin-gated:
  - :mod:`romarr.metadata.api.providers`       — /api/v3/metadata/provider*
  - :mod:`romarr.metadata.api.field_priority`  — /api/v3/metadata/field-priority*
  - :mod:`romarr.metadata.api.refresh`         — /api/v3/game/{id}/refresh-metadata
"""

from romarr.metadata.api.field_priority import router as field_priority_router
from romarr.metadata.api.providers import router as providers_router
from romarr.metadata.api.refresh import router as refresh_router

__all__ = [
    "field_priority_router",
    "providers_router",
    "refresh_router",
]
