"""FastAPI routers for the profiles feature.

Six routers, all admin-gated for mutations + the naming-preview;
reads accessible to any authenticated user (FR-032a):

  * :mod:`romarr.profiles.api.quality`        — /api/v3/qualityprofile
  * :mod:`romarr.profiles.api.region`         — /api/v3/rom/regionprofile
  * :mod:`romarr.profiles.api.dump`           — /api/v3/rom/dumpprofile
  * :mod:`romarr.profiles.api.language`       — /api/v3/rom/languageprofile
  * :mod:`romarr.profiles.api.naming`         — /api/v3/rom/namingprofile + /preview
  * :mod:`romarr.profiles.api.custom_format`  — /api/v3/customformat

Mounted in :func:`romarr.api.app.create_app`.
"""

from romarr.profiles.api.custom_format import router as custom_format_router
from romarr.profiles.api.dump import router as dump_profile_router
from romarr.profiles.api.language import router as language_profile_router
from romarr.profiles.api.naming import router as naming_profile_router
from romarr.profiles.api.quality import router as quality_profile_router
from romarr.profiles.api.region import router as region_profile_router

__all__ = [
    "custom_format_router",
    "dump_profile_router",
    "language_profile_router",
    "naming_profile_router",
    "quality_profile_router",
    "region_profile_router",
]
