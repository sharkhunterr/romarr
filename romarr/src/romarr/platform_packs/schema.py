"""JSON Schema for the YAML pack format (Draft 2020-12).

The schema lives here as a Python dict so the validator doesn't need
filesystem access at import time. It mirrors the canonical schema in
``specs/003-platform-packs/data-model.md`` verbatim.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

# Maximum schema_version we know how to interpret. Pack uploads with a
# higher number are rejected via :class:`SchemaVersionTooHighError`.
SUPPORTED_SCHEMA_VERSION: int = 1


PACK_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://romarr.example/schemas/platform-pack-v1.json",
    "title": "Romarr Platform Pack",
    "type": "object",
    "additionalProperties": False,
    "required": ["pack_version", "schema_version", "platforms"],
    "properties": {
        "pack_version": {
            "type": "string",
            "pattern": r"^[0-9]{4}\.[0-9]{2}\.[0-9]{3}$",
            "description": "Date-based version, YYYY.MM.NNN",
        },
        "schema_version": {"type": "integer", "minimum": 1, "maximum": 1},
        "description": {"type": "string"},
        "author": {"type": "string"},
        "source_url": {"type": "string", "format": "uri"},
        "parsing_strategies": {
            "type": "array",
            "items": {"$ref": "#/$defs/parsingStrategy"},
        },
        "platforms": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/platform"},
        },
    },
    "$defs": {
        "platform": {
            "type": "object",
            "additionalProperties": False,
            "required": ["slug", "name", "manufacturer", "formats"],
            "properties": {
                "slug": {
                    "type": "string",
                    "pattern": r"^[a-z0-9]+(-[a-z0-9]+)*$",
                },
                "name": {"type": "string", "minLength": 1},
                "short_name": {"type": "string"},
                "manufacturer": {"type": "string"},
                "generation": {"type": "integer", "minimum": 1},
                "release_year": {
                    "type": "integer",
                    "minimum": 1970,
                    "maximum": 2100,
                },
                "is_handheld": {"type": "boolean"},
                "is_disc_based": {"type": "boolean"},
                "parent_platform_slug": {
                    "type": ["string", "null"],
                    "pattern": r"^[a-z0-9]+(-[a-z0-9]+)*$",
                },
                "metadata_ids": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "igdb_id": {"type": ["integer", "null"]},
                        "screenscraper_id": {"type": ["integer", "null"]},
                        "mobygames_id": {"type": ["integer", "null"]},
                        "thegamesdb_id": {"type": ["integer", "null"]},
                        "launchbox_id": {"type": ["string", "null"]},
                        "hasheous_id": {"type": ["string", "null"]},
                        "retroachievements_id": {
                            "type": ["integer", "null"]
                        },
                    },
                },
                "icon_url": {"type": "string", "format": "uri"},
                "formats": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/$defs/format"},
                },
                "naming_tokens": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/namingToken"},
                },
            },
        },
        "format": {
            "type": "object",
            "additionalProperties": False,
            "required": ["extension", "format_type"],
            "properties": {
                "extension": {
                    "type": "string",
                    "pattern": r"^\.[A-Za-z0-9]+$",
                },
                "format_type": {
                    "type": "string",
                    "enum": [
                        "cartridge",
                        "disc",
                        "compressed",
                        "archive",
                        "package",
                    ],
                },
                "is_primary": {"type": "boolean"},
                "is_compressed": {"type": "boolean"},
                "requires_companion": {"type": "boolean"},
                "companion_extensions": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": r"^\.[A-Za-z0-9]+$",
                    },
                },
                "parser_strategy": {"type": "string"},
                "header_offset": {"type": "integer", "minimum": 0},
                "header_signature_hex": {
                    "type": "string",
                    "pattern": r"^[0-9A-Fa-f]+$",
                },
            },
        },
        "namingToken": {
            "type": "object",
            "additionalProperties": False,
            "required": ["pattern", "meaning"],
            "properties": {
                "pattern": {"type": "string", "minLength": 1},
                "meaning": {
                    "type": "string",
                    "enum": ["serial", "revision", "content_type", "custom"],
                },
                "description": {"type": "string"},
                "example": {"type": "string"},
            },
        },
        "parsingStrategy": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "regex"],
            "properties": {
                "id": {
                    "type": "string",
                    "pattern": r"^[a-z0-9]+(-[a-z0-9]+)*$",
                },
                "description": {"type": "string"},
                "regex": {"type": "string", "minLength": 1},
                "apply_to_platforms": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": r"^[a-z0-9]+(-[a-z0-9]+)*$",
                    },
                },
            },
        },
    },
}


_validator: Draft202012Validator | None = None


def get_validator() -> Draft202012Validator:
    """Lazily-instantiate and cache the JSON Schema validator."""
    global _validator
    if _validator is None:
        _validator = Draft202012Validator(PACK_SCHEMA)
    return _validator
