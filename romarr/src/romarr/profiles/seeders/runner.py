"""Idempotent default-profile seeder (T053-T055).

Pure orchestration on top of the persistence layer:

  * loads JSON catalogues from this package's directory;
  * validates each row through its matching Pydantic ``*Create``
    schema (so the seeder shares the same validation rules as the
    API);
  * upserts by ``seed_key`` only when ``is_user_modified = false``
    (FR-003a) — and only when the persisted row's payload actually
    differs from the JSON, so a re-run on a steady-state DB is a
    no-op (T051 idempotent rerun).

Why JSON files (and not Python constants)? Diff-friendly across
releases + future "reset to factory defaults" can re-read the JSON
without a migration. The runner also serves the small
``scene_groups.json`` config-file for the foundation parser's
release_group extraction (FR-024).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from romarr.profiles.models import (
    CustomFormat,
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)
from romarr.profiles.schemas import (
    CustomFormatCreate,
    DumpProfileCreate,
    LanguageProfileCreate,
    NamingProfileCreate,
    QualityProfileCreate,
    RegionProfileCreate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

SEED_DIR = Path(__file__).resolve().parent
"""Directory holding the JSON seed files. Tests can monkey-patch
this attribute to point at a controlled fixture set."""


# ---------------------------------------------------------------------------
# JSON load helper (defined early so module-level constants below can use it)
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Any:
    """Load a JSON file. Callers narrow the return type — the seed
    files are either a list of dicts (profile catalogues) or a list
    of strings (scene_groups.json)."""
    with path.open() as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Seed catalogue dispatch table
# ---------------------------------------------------------------------------


def _quality_payload(create: QualityProfileCreate) -> dict[str, Any]:
    return {
        "name": create.name,
        "allowed_formats": create.allowed_formats,
        "preferred_format": create.preferred_format,
        "require_dat_verified": create.require_dat_verified,
        "allow_archive_double_compression": create.allow_archive_double_compression,
        "upgrade_until_format": create.upgrade_until_format,
        "auto_grab_min_score": create.auto_grab_min_score,
    }


def _region_payload(create: RegionProfileCreate) -> dict[str, Any]:
    return {
        "name": create.name,
        "priorities": create.priorities,
        "allow_fallback_outside_priorities": create.allow_fallback_outside_priorities,
        "exclude_regions": create.exclude_regions,
    }


def _dump_payload(create: DumpProfileCreate) -> dict[str, Any]:
    return {
        "name": create.name,
        "allowed_dump_status": create.allowed_dump_status,
        "allow_proto_beta": create.allow_proto_beta,
        "allow_hacks": create.allow_hacks,
        "allow_trainers": create.allow_trainers,
        "allow_translations": create.allow_translations,
        "prefer_revision": create.prefer_revision,
    }


def _language_payload(create: LanguageProfileCreate) -> dict[str, Any]:
    return {
        "name": create.name,
        "required_languages": create.required_languages,
        "preferred_languages": create.preferred_languages,
        "exclude_japanese_only": create.exclude_japanese_only,
    }


def _naming_payload(create: NamingProfileCreate) -> dict[str, Any]:
    return {
        "name": create.name,
        "convention": create.convention,
        "template": create.template,
        "platform_subfolder": create.platform_subfolder,
        "replace_illegal_chars": create.replace_illegal_chars,
        "multi_disc_subfolder": create.multi_disc_subfolder,
    }


def _custom_format_payload(create: CustomFormatCreate) -> dict[str, Any]:
    return {
        "name": create.name,
        "score": create.score,
        "conditions": [c.model_dump(by_alias=True, exclude_none=True) for c in create.conditions],
    }


# Tuple of (json filename, model class, *Create schema, payload extractor).
# Iteration order is the catalogue order documented in data-model.md.
_CATALOGUE: list[tuple[str, type[Any], type[Any], Any]] = [
    ("quality.json", QualityProfile, QualityProfileCreate, _quality_payload),
    ("region.json", RegionProfile, RegionProfileCreate, _region_payload),
    ("dump.json", DumpProfile, DumpProfileCreate, _dump_payload),
    ("language.json", LanguageProfile, LanguageProfileCreate, _language_payload),
    ("naming.json", NamingProfile, NamingProfileCreate, _naming_payload),
    (
        "custom_formats.json",
        CustomFormat,
        CustomFormatCreate,
        _custom_format_payload,
    ),
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def seed_defaults(
    session: AsyncSession, *, seed_dir: Path | None = None
) -> dict[str, int]:
    """Apply every default-profile JSON. Returns ``{"<table>": rows_changed}``.

    ``rows_changed`` counts inserts + updates; rows that were already
    in the desired state contribute 0 (T051 idempotency).

    Pass ``seed_dir`` to point at an alternate JSON directory — used
    by tests to feed a controlled catalogue without monkey-patching
    the module-level :data:`SEED_DIR`.
    """
    where = seed_dir or SEED_DIR
    counts: dict[str, int] = {}

    for filename, model_cls, schema_cls, extract_payload in _CATALOGUE:
        rows = _load_json(where / filename)
        if not isinstance(rows, list):
            raise ValueError(f"{filename} must be a JSON list of objects")
        changed = 0
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError(
                    f"{filename}: every entry must be a JSON object"
                )
            seed_key = raw.get("seed_key")
            if not seed_key:
                raise ValueError(f"{filename}: every row needs a seed_key")
            create = schema_cls(**{k: v for k, v in raw.items() if k != "seed_key"})
            payload = extract_payload(create)

            existing = (
                await session.execute(
                    select(model_cls).where(model_cls.seed_key == seed_key)
                )
            ).scalar_one_or_none()

            if existing is None:
                row = model_cls(
                    seed_key=seed_key,
                    is_factory_default=True,
                    is_user_modified=False,
                    **payload,
                )
                session.add(row)
                changed += 1
                continue

            if existing.is_user_modified:
                # Operator owns this row; never overwrite.
                continue

            # Seeded row that nobody has touched — refresh in place if
            # the JSON has drifted from what's in the DB.
            if _payload_matches(existing, payload):
                continue
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.is_factory_default = True
            changed += 1

        counts[filename] = changed

    await session.commit()
    return counts


# ---------------------------------------------------------------------------
# Scene groups (used by the foundation parser, not a profile entity)
# ---------------------------------------------------------------------------


def load_scene_groups(seed_dir: Path | None = None) -> list[str]:
    """Read ``scene_groups.json`` and return the canonical list."""
    where = seed_dir or SEED_DIR
    raw = _load_json(where / "scene_groups.json")
    if not isinstance(raw, list):
        raise ValueError("scene_groups.json must be a JSON list of strings")
    return [str(item) for item in raw]


SCENE_GROUPS: list[str] = load_scene_groups()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload_matches(existing: Any, payload: Mapping[str, Any]) -> bool:
    """True when every payload field on ``existing`` already matches.

    Skips ``is_factory_default`` / ``is_user_modified`` / ``seed_key``
    / timestamp columns which the seeder never derives from the JSON.
    """
    for key, expected in payload.items():
        actual = getattr(existing, key)
        if isinstance(expected, list) and isinstance(actual, list):
            if list(actual) != list(expected):
                return False
        elif actual != expected:
            return False
    return True


# Suppress unused-import lint noise — Iterable is used implicitly via
# the signature documentation.
_ = Iterable
