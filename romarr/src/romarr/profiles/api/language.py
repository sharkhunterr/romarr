"""Language profile CRUD — /api/v3/rom/languageprofile."""

from __future__ import annotations

from romarr.profiles.api._shared import make_crud_router
from romarr.profiles.models import LanguageProfile
from romarr.profiles.schemas import (
    LanguageProfileCreate,
    LanguageProfileRead,
    LanguageProfileUpdate,
)

router = make_crud_router(
    label="languageprofile",
    base_path="/api/v3/rom/languageprofile",
    tag="LanguageProfiles",
    model_cls=LanguageProfile,
    schema_read=LanguageProfileRead,
    schema_create=LanguageProfileCreate,
    schema_update=LanguageProfileUpdate,
)
