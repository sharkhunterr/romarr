"""Dump profile CRUD — /api/v3/rom/dumpprofile."""

from __future__ import annotations

from romarr.profiles.api._shared import make_crud_router
from romarr.profiles.models import DumpProfile
from romarr.profiles.schemas import (
    DumpProfileCreate,
    DumpProfileRead,
    DumpProfileUpdate,
)

router = make_crud_router(
    label="dumpprofile",
    base_path="/api/v3/rom/dumpprofile",
    tag="DumpProfiles",
    model_cls=DumpProfile,
    schema_read=DumpProfileRead,
    schema_create=DumpProfileCreate,
    schema_update=DumpProfileUpdate,
)
