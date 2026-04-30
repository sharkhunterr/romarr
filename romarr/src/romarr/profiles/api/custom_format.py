"""Custom Format CRUD — /api/v3/customformat."""

from __future__ import annotations

from romarr.profiles.api._shared import make_crud_router
from romarr.profiles.models import CustomFormat
from romarr.profiles.schemas import (
    CustomFormatCreate,
    CustomFormatRead,
    CustomFormatUpdate,
)

router = make_crud_router(
    label="customformat",
    base_path="/api/v3/customformat",
    tag="CustomFormats",
    model_cls=CustomFormat,
    schema_read=CustomFormatRead,
    schema_create=CustomFormatCreate,
    schema_update=CustomFormatUpdate,
)
