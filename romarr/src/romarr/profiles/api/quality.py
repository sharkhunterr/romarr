"""Quality profile CRUD — /api/v3/qualityprofile."""

from __future__ import annotations

from romarr.profiles.api._shared import make_crud_router
from romarr.profiles.models import QualityProfile
from romarr.profiles.schemas import (
    QualityProfileCreate,
    QualityProfileRead,
    QualityProfileUpdate,
)

router = make_crud_router(
    label="qualityprofile",
    base_path="/api/v3/qualityprofile",
    tag="QualityProfiles",
    model_cls=QualityProfile,
    schema_read=QualityProfileRead,
    schema_create=QualityProfileCreate,
    schema_update=QualityProfileUpdate,
)
