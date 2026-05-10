"""Pydantic v2 Read/Create/Update DTOs for every foundation entity.

Per FR-008 each entity exposes three shapes:
  * ``*Read``   — what the API returns (every column populated).
  * ``*Create`` — what the API accepts on POST (subset; server fills timestamps).
  * ``*Update`` — what the API accepts on PUT (all fields optional).

Schemas are ``extra='forbid'`` so unknown fields are rejected with HTTP
422 by FastAPI's default behaviour. The ``model_config`` picks up
``from_attributes=True`` so we can hydrate Read schemas directly from
SQLAlchemy ORM rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.validators import (
    require_at_least_one_hash,
    validate_crc32,
    validate_language_list,
    validate_md5,
    validate_region_list,
    validate_sha1,
    validate_sha256,
    validate_slug,
)


class _SchemaBase(BaseModel):
    """Common Pydantic config — strict, ORM-friendly."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------


class PlatformCreate(_SchemaBase):
    slug: Annotated[str, Field(max_length=64)]
    name: Annotated[str, Field(max_length=128)]
    short_name: Annotated[str | None, Field(max_length=32)] = None
    manufacturer: Annotated[str | None, Field(max_length=64)] = None
    release_year: int | None = None
    parent_platform_id: int | None = None
    igdb_id: int | None = None
    screenscraper_id: int | None = None
    mobygames_id: int | None = None
    launchbox_id: int | None = None
    retroachievements_id: int | None = None
    newznab_category_ids: list[int] = Field(default_factory=list)
    pack_source: str = "builtin"
    pack_version: Annotated[str | None, Field(max_length=16)] = None
    extra_meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_slug(self) -> PlatformCreate:
        validate_slug(self.slug)
        return self


class PlatformUpdate(_SchemaBase):
    name: Annotated[str | None, Field(max_length=128)] = None
    short_name: Annotated[str | None, Field(max_length=32)] = None
    manufacturer: Annotated[str | None, Field(max_length=64)] = None
    release_year: int | None = None
    parent_platform_id: int | None = None
    igdb_id: int | None = None
    screenscraper_id: int | None = None
    mobygames_id: int | None = None
    launchbox_id: int | None = None
    retroachievements_id: int | None = None
    newznab_category_ids: list[int] | None = None
    pack_source: str | None = None
    pack_version: Annotated[str | None, Field(max_length=16)] = None
    extra_meta: dict[str, Any] | None = None


class PlatformRead(PlatformCreate):
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PlatformFormat
# ---------------------------------------------------------------------------


class PlatformFormatCreate(_SchemaBase):
    platform_id: int
    extension: Annotated[str, Field(max_length=16)]
    format_type: Annotated[str, Field(max_length=16)]
    min_size_bytes: int | None = None
    max_size_bytes: int | None = None
    pack_source: str = "builtin"


class PlatformFormatUpdate(_SchemaBase):
    extension: Annotated[str | None, Field(max_length=16)] = None
    format_type: Annotated[str | None, Field(max_length=16)] = None
    min_size_bytes: int | None = None
    max_size_bytes: int | None = None
    pack_source: str | None = None


class PlatformFormatRead(PlatformFormatCreate):
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PlatformNamingToken
# ---------------------------------------------------------------------------


class PlatformNamingTokenCreate(_SchemaBase):
    platform_id: int
    name: Annotated[str, Field(max_length=64)]
    pattern: Annotated[str, Field(max_length=512)]
    meaning: Annotated[str, Field(max_length=64)]
    convention: NamingConvention = NamingConvention.NO_INTRO
    pack_source: str = "builtin"


class PlatformNamingTokenUpdate(_SchemaBase):
    name: Annotated[str | None, Field(max_length=64)] = None
    pattern: Annotated[str | None, Field(max_length=512)] = None
    meaning: Annotated[str | None, Field(max_length=64)] = None
    convention: NamingConvention | None = None
    pack_source: str | None = None


class PlatformNamingTokenRead(PlatformNamingTokenCreate):
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------


class GameCreate(_SchemaBase):
    platform_id: int
    slug: Annotated[str, Field(max_length=192)]
    title: Annotated[str, Field(max_length=255)]
    sort_title: Annotated[str | None, Field(max_length=255)] = None
    summary: str | None = None
    cover_path: str | None = None
    igdb_id: int | None = None
    mobygames_id: int | None = None
    screenscraper_id: int | None = None
    launchbox_id: int | None = None
    retroachievements_id: int | None = None
    release_date: datetime | None = None
    developer: Annotated[str | None, Field(max_length=128)] = None
    publisher: Annotated[str | None, Field(max_length=128)] = None
    rating: float | None = None
    age_rating: Annotated[str | None, Field(max_length=16)] = None
    players_min: int | None = None
    players_max: int | None = None
    hltb_main: int | None = None
    achievements_count: int | None = None
    genres: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    franchises: list[str] = Field(default_factory=list)
    tags: list[int] = Field(default_factory=list)
    locked_fields: list[str] = Field(default_factory=list)
    custom_metadata: dict[str, Any] = Field(default_factory=dict)
    monitored: bool = True
    needs_metadata_refresh: bool = False
    notes: str | None = None
    library_id: int | None = None

    @model_validator(mode="after")
    def _check_slug(self) -> GameCreate:
        validate_slug(self.slug)
        return self


class GameUpdate(_SchemaBase):
    title: Annotated[str | None, Field(max_length=255)] = None
    sort_title: Annotated[str | None, Field(max_length=255)] = None
    summary: str | None = None
    cover_path: str | None = None
    igdb_id: int | None = None
    mobygames_id: int | None = None
    screenscraper_id: int | None = None
    launchbox_id: int | None = None
    retroachievements_id: int | None = None
    release_date: datetime | None = None
    developer: Annotated[str | None, Field(max_length=128)] = None
    publisher: Annotated[str | None, Field(max_length=128)] = None
    rating: float | None = None
    age_rating: Annotated[str | None, Field(max_length=16)] = None
    players_min: int | None = None
    players_max: int | None = None
    hltb_main: int | None = None
    achievements_count: int | None = None
    genres: list[str] | None = None
    themes: list[str] | None = None
    franchises: list[str] | None = None
    tags: list[int] | None = None
    locked_fields: list[str] | None = None
    custom_metadata: dict[str, Any] | None = None
    monitored: bool | None = None
    needs_metadata_refresh: bool | None = None
    library_id: int | None = None


class GameRead(GameCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    # Slice 394 — derived "do we already have this game on disk?"
    # flag, projected by the API list/read endpoints from the
    # Release/Dump tables. ``True`` when at least one Release
    # has ``status='imported'`` or ``'cutoff_met'``. Optional so
    # the schema stays usable from contexts that don't enrich
    # (writes, the lookup-add endpoint, …).
    acquired: bool | None = None


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------


class ReleaseCreate(_SchemaBase):
    game_id: int
    name: Annotated[str, Field(max_length=255)]
    original_name: Annotated[str | None, Field(max_length=255)] = None
    regions: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    revision: Annotated[str | None, Field(max_length=32)] = None
    dump_status: DumpStatus = DumpStatus.UNKNOWN
    naming_convention: NamingConvention = NamingConvention.UNKNOWN
    tags: list[str] = Field(default_factory=list)
    disc_number: int = 1
    disc_total: int = 1
    parent_release_id: int | None = None
    status: str = "wanted"
    monitored: bool = True
    cutoff_met: bool = False

    @model_validator(mode="after")
    def _check(self) -> ReleaseCreate:
        # Normalize regions/languages — sorted, dedup'd, validated.
        object.__setattr__(self, "regions", validate_region_list(self.regions))
        object.__setattr__(self, "languages", validate_language_list(self.languages))

        # Multi-disc invariant (FR-004)
        from romarr.domain.validators import validate_multi_disc

        validate_multi_disc(
            disc_number=self.disc_number,
            disc_total=self.disc_total,
            parent_release_id=self.parent_release_id,
        )
        return self


class ReleaseUpdate(_SchemaBase):
    name: Annotated[str | None, Field(max_length=255)] = None
    original_name: Annotated[str | None, Field(max_length=255)] = None
    regions: list[str] | None = None
    languages: list[str] | None = None
    revision: Annotated[str | None, Field(max_length=32)] = None
    dump_status: DumpStatus | None = None
    naming_convention: NamingConvention | None = None
    tags: list[str] | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    parent_release_id: int | None = None
    status: str | None = None
    monitored: bool | None = None
    cutoff_met: bool | None = None


class ReleaseRead(ReleaseCreate):
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------


class DumpCreate(_SchemaBase):
    release_id: int
    path: str
    original_filename: str
    size_bytes: int
    format: Annotated[str, Field(max_length=16)]
    crc32: str
    md5: str
    sha1: str
    sha256: str | None = None
    dat_verified: bool = False
    dat_source: Annotated[str | None, Field(max_length=16)] = None
    dat_entry_id: int | None = None
    imported_at: datetime | None = None
    imported_by: Annotated[str, Field(max_length=32)] = "system"
    imported_via: Annotated[str | None, Field(max_length=16)] = None

    @model_validator(mode="after")
    def _check(self) -> DumpCreate:
        validate_crc32(self.crc32)
        validate_md5(self.md5)
        validate_sha1(self.sha1)
        if self.sha256 is not None:
            validate_sha256(self.sha256)
        return self


class DumpUpdate(_SchemaBase):
    path: str | None = None
    dat_verified: bool | None = None
    dat_source: Annotated[str | None, Field(max_length=16)] = None
    dat_entry_id: int | None = None
    imported_at: datetime | None = None
    imported_by: Annotated[str | None, Field(max_length=32)] = None
    imported_via: Annotated[str | None, Field(max_length=16)] = None


class DumpRead(DumpCreate):
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# DatEntry
# ---------------------------------------------------------------------------


class DatEntryCreate(_SchemaBase):
    platform_id: int
    source: Annotated[str, Field(max_length=32)]
    name: Annotated[str, Field(max_length=255)]
    description: str | None = None
    size_bytes: int | None = None
    crc32: str | None = None
    md5: str | None = None
    sha1: str | None = None
    status: DumpStatus = DumpStatus.VERIFIED
    dat_contents_hash: Annotated[str, Field(max_length=64)]

    @model_validator(mode="after")
    def _check(self) -> DatEntryCreate:
        require_at_least_one_hash(
            crc32=self.crc32, md5=self.md5, sha1=self.sha1
        )
        if self.crc32 is not None:
            validate_crc32(self.crc32)
        if self.md5 is not None:
            validate_md5(self.md5)
        if self.sha1 is not None:
            validate_sha1(self.sha1)
        return self


class DatEntryUpdate(_SchemaBase):
    name: Annotated[str | None, Field(max_length=255)] = None
    description: str | None = None
    size_bytes: int | None = None
    status: DumpStatus | None = None


class DatEntryRead(DatEntryCreate):
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# UnidentifiedDump
# ---------------------------------------------------------------------------


class UnidentifiedDumpCreate(_SchemaBase):
    path: str
    size_bytes: int
    discovered_at: datetime
    crc32: str | None = None
    md5: str | None = None
    sha1: str | None = None
    attempt_count: int = 0
    last_attempt_at: datetime | None = None
    last_error: str | None = None
    suggested_platform_id: int | None = None


class UnidentifiedDumpUpdate(_SchemaBase):
    attempt_count: int | None = None
    last_attempt_at: datetime | None = None
    last_error: str | None = None
    suggested_platform_id: int | None = None


class UnidentifiedDumpRead(UnidentifiedDumpCreate):
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PlatformPack
# ---------------------------------------------------------------------------


class PlatformPackCreate(_SchemaBase):
    pack_version: Annotated[str, Field(max_length=16)]
    schema_version: int = 1
    description: str | None = None
    author: Annotated[str | None, Field(max_length=128)] = None
    source_url: str | None = None
    contents_hash: Annotated[str, Field(max_length=64)]
    pack_source: str = "builtin"
    applied_at: datetime
    applied_by: Annotated[str, Field(max_length=32)] = "system"


class PlatformPackUpdate(_SchemaBase):
    description: str | None = None
    author: Annotated[str | None, Field(max_length=128)] = None
    source_url: str | None = None


class PlatformPackRead(PlatformPackCreate):
    id: int
    created_at: datetime
    updated_at: datetime
