"""Handler backup — CustomFormat (scoring des releases).

Mono-table, dedup par name, colonnes JSON (`conditions`). Aucun secret.
"""
from __future__ import annotations

from romarr.backup.handlers._shared import SimpleModelHandler
from romarr.backup.registry import register
from romarr.backup.schemas import ResourceKey
from romarr.profiles.models import CustomFormat


class CustomFormatHandler(SimpleModelHandler):
    key = ResourceKey.CUSTOM_FORMATS
    label = "Custom Formats"
    model_class = CustomFormat
    FIELDS = [
        "name",
        "score",
        "conditions",
        "seed_key",
        "is_user_modified",
        "is_factory_default",
    ]


register(CustomFormatHandler())
