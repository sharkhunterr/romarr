"""Pydantic schemas for the profiles HTTP layer.

Each profile type has the standard ``*Read / *Create / *Update``
triplet. Cross-field validators (``preferred_format ∈ allowed_formats``,
``len(priorities) >= 1 OR fallback=true``, etc.) live as
:func:`pydantic.model_validator` runs — too rich for SQL CHECK and
shared between the create + update paths.

``NamingPreviewRequest`` references :class:`NamingProfileCreate`
which is why it lives here, not in :mod:`romarr.profiles.types`.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from romarr.profiles.errors import RegexCompileError


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


class QualityProfileRead(_Base):
    id: int
    name: str
    allowed_formats: list[str]
    preferred_format: str
    require_dat_verified: bool
    allow_archive_double_compression: bool
    upgrade_until_format: str
    is_factory_default: bool
    is_user_modified: bool
    seed_key: str | None
    created_at: datetime
    updated_at: datetime


class QualityProfileCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    allowed_formats: Annotated[list[str], Field(min_length=1)]
    preferred_format: Annotated[str, Field(min_length=1, max_length=32)]
    require_dat_verified: bool = False
    allow_archive_double_compression: bool = False
    upgrade_until_format: Annotated[str, Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.preferred_format not in self.allowed_formats:
            raise ValueError(
                "preferred_format must be one of allowed_formats"
            )
        if self.upgrade_until_format not in self.allowed_formats:
            raise ValueError(
                "upgrade_until_format must be one of allowed_formats"
            )
        return self


class QualityProfileUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    allowed_formats: list[str] | None = None
    preferred_format: Annotated[str | None, Field(default=None, max_length=32)] = None
    require_dat_verified: bool | None = None
    allow_archive_double_compression: bool | None = None
    upgrade_until_format: Annotated[str | None, Field(default=None, max_length=32)] = None


# ---------------------------------------------------------------------------
# Region
# ---------------------------------------------------------------------------


class RegionProfileRead(_Base):
    id: int
    name: str
    priorities: list[str]
    allow_fallback_outside_priorities: bool
    exclude_regions: list[str]
    is_factory_default: bool
    is_user_modified: bool
    seed_key: str | None
    created_at: datetime
    updated_at: datetime


class RegionProfileCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    priorities: list[str] = Field(default_factory=list)
    allow_fallback_outside_priorities: bool = True
    exclude_regions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.priorities and not self.allow_fallback_outside_priorities:
            raise ValueError(
                "priorities cannot be empty when fallback is disabled "
                "(profile would reject every release)"
            )
        overlap = set(self.priorities) & set(self.exclude_regions)
        if overlap:
            raise ValueError(
                f"region(s) appear in both priorities and exclude_regions: {sorted(overlap)!r}"
            )
        return self


class RegionProfileUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    priorities: list[str] | None = None
    allow_fallback_outside_priorities: bool | None = None
    exclude_regions: list[str] | None = None


# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------


_PreferRevision = Literal["latest", "first", "any"]


class DumpProfileRead(_Base):
    id: int
    name: str
    allowed_dump_status: list[str]
    allow_proto_beta: bool
    allow_hacks: bool
    allow_trainers: bool
    allow_translations: bool
    prefer_revision: str
    is_factory_default: bool
    is_user_modified: bool
    seed_key: str | None
    created_at: datetime
    updated_at: datetime


class DumpProfileCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    allowed_dump_status: list[str] = Field(default_factory=lambda: ["verified"])
    allow_proto_beta: bool = False
    allow_hacks: bool = False
    allow_trainers: bool = False
    allow_translations: bool = False
    prefer_revision: _PreferRevision = "latest"


class DumpProfileUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    allowed_dump_status: list[str] | None = None
    allow_proto_beta: bool | None = None
    allow_hacks: bool | None = None
    allow_trainers: bool | None = None
    allow_translations: bool | None = None
    prefer_revision: _PreferRevision | None = None


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------


class LanguageProfileRead(_Base):
    id: int
    name: str
    required_languages: list[str]
    preferred_languages: list[str]
    exclude_japanese_only: bool
    is_factory_default: bool
    is_user_modified: bool
    seed_key: str | None
    created_at: datetime
    updated_at: datetime


class LanguageProfileCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    required_languages: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    exclude_japanese_only: bool = True


class LanguageProfileUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    required_languages: list[str] | None = None
    preferred_languages: list[str] | None = None
    exclude_japanese_only: bool | None = None


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


_NamingConvention = Literal["no-intro", "redump", "tosec", "es-de", "romm", "custom"]


class NamingProfileRead(_Base):
    id: int
    name: str
    convention: str
    template: str
    platform_subfolder: bool
    replace_illegal_chars: bool
    multi_disc_subfolder: bool
    is_factory_default: bool
    is_user_modified: bool
    seed_key: str | None
    created_at: datetime
    updated_at: datetime


class NamingProfileCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    convention: _NamingConvention
    template: Annotated[str, Field(min_length=1)]
    platform_subfolder: bool = True
    replace_illegal_chars: bool = True
    multi_disc_subfolder: bool = True


class NamingProfileUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    convention: _NamingConvention | None = None
    template: Annotated[str | None, Field(default=None, min_length=1)] = None
    platform_subfolder: bool | None = None
    replace_illegal_chars: bool | None = None
    multi_disc_subfolder: bool | None = None


# ---------------------------------------------------------------------------
# Custom Format
# ---------------------------------------------------------------------------


class CustomFormatCondition(_Base):
    """One row of a Custom Format's condition list.

    ``or`` carries optional alternates for the OR-grouping path
    (FR-021); when present, the parent condition matches if ANY of
    its sub-conditions match. Validators reject invalid combinations
    (e.g., ``greater_than`` with a non-numeric field).
    """

    field: Literal[
        "tags",
        "region",
        "format",
        "dump_status",
        "release_group",
        "indexer_source",
        "languages",
        "revision",
        "naming_convention",
        "release_size",
    ]
    operator: Literal[
        "matches_regex",
        "equals",
        "in",
        "contains",
        "not_in",
        "greater_than",
        "less_than",
    ]
    values: str | int | float | list[str | int | float]
    or_: list[CustomFormatCondition] | None = Field(default=None, alias="or")

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.operator in ("greater_than", "less_than"):
            if self.field != "release_size":
                raise ValueError(
                    f"operator {self.operator!r} only valid with field='release_size'"
                )
            if not isinstance(self.values, int | float):
                raise ValueError(
                    f"operator {self.operator!r} requires a numeric value"
                )
        if self.operator in ("in", "not_in") and not isinstance(self.values, list):
            raise ValueError(
                f"operator {self.operator!r} requires a list value"
            )
        if self.operator == "matches_regex":
            if not isinstance(self.values, str):
                raise ValueError("matches_regex requires a string pattern")
            try:
                re.compile(self.values)
            except re.error as exc:
                raise RegexCompileError(
                    f"invalid regex {self.values!r}: {exc}"
                ) from exc
        return self


class CustomFormatRead(_Base):
    id: int
    name: str
    score: int
    conditions: list[dict[str, Any]]
    is_factory_default: bool
    is_user_modified: bool
    seed_key: str | None
    created_at: datetime
    updated_at: datetime


class CustomFormatCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    score: Annotated[int, Field(ge=-10000, le=10000)]
    conditions: Annotated[list[CustomFormatCondition], Field(min_length=1)]


class CustomFormatUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    score: Annotated[int | None, Field(default=None, ge=-10000, le=10000)] = None
    conditions: list[CustomFormatCondition] | None = None


# ---------------------------------------------------------------------------
# Naming preview
# ---------------------------------------------------------------------------


class NamingPreviewRequest(_Base):
    profile: NamingProfileCreate
    sample_release_id: int


CustomFormatCondition.model_rebuild()


__all__ = [
    "CustomFormatCondition",
    "CustomFormatCreate",
    "CustomFormatRead",
    "CustomFormatUpdate",
    "DumpProfileCreate",
    "DumpProfileRead",
    "DumpProfileUpdate",
    "LanguageProfileCreate",
    "LanguageProfileRead",
    "LanguageProfileUpdate",
    "NamingPreviewRequest",
    "NamingProfileCreate",
    "NamingProfileRead",
    "NamingProfileUpdate",
    "QualityProfileCreate",
    "QualityProfileRead",
    "QualityProfileUpdate",
    "RegionProfileCreate",
    "RegionProfileRead",
    "RegionProfileUpdate",
]
