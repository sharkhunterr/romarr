"""Region profile CRUD — /api/v3/rom/regionprofile."""

from __future__ import annotations

from romarr.profiles.api._shared import make_crud_router
from romarr.profiles.models import RegionProfile
from romarr.profiles.schemas import (
    RegionProfileCreate,
    RegionProfileRead,
    RegionProfileUpdate,
)

router = make_crud_router(
    label="regionprofile",
    base_path="/api/v3/rom/regionprofile",
    tag="RegionProfiles",
    model_cls=RegionProfile,
    schema_read=RegionProfileRead,
    schema_create=RegionProfileCreate,
    schema_update=RegionProfileUpdate,
)
