"""SQLAlchemy models for the profiles feature.

Six profile tables (Quality, Region, Dump, Language, Naming,
Custom Format) plus the ``library_custom_format`` m2m. Per the
clarification chain in `data-model.md`:

  - Every profile table carries ``seed_key`` (NULL-when-not-seeded)
    and ``is_user_modified`` (FR-003a). The seeder upserts by
    ``seed_key`` only when ``is_user_modified = false``; UPDATE
    through any API endpoint flips the flag in the same transaction.

  - The ``library_custom_format`` m2m is created here with both
    columns + composite PK + the FK on ``custom_format_id``. The
    deferred FK on ``library_id`` lands in spec 009's migration once
    the ``library`` table exists. Same forward-reference pattern as
    spec 005's ``indexer.download_client_id``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_PREFER_REVISION_CHECK = "prefer_revision IN ('latest','first','any')"
_NAMING_CONVENTION_CHECK = (
    "convention IN ('no-intro','redump','tosec','es-de','romm','custom')"
)
_CUSTOM_FORMAT_SCORE_CHECK = "score BETWEEN -10000 AND 10000"


class _ProfileMixin(TimestampMixin):
    """Shared columns across the six profile tables.

    ``seed_key`` is the seeder's identity column — when set, the
    seeder owns the row and may upsert. ``is_user_modified`` flips
    to true on any API mutation; the seeder skips rows where it's
    true (FR-003a).
    """

    seed_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_user_modified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_factory_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class QualityProfile(Base, _ProfileMixin):
    __tablename__ = "quality_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_formats: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    preferred_format: Mapped[str] = mapped_column(String(32), nullable=False)
    require_dat_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    allow_archive_double_compression: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    upgrade_until_format: Mapped[str] = mapped_column(String(32), nullable=False)
    # Minimum ``score_breakdown.total`` a candidate must reach for
    # the RSS / on-add auto-grab paths to dispatch it. Default 0
    # keeps the legacy "grab anything that cleared the pipeline"
    # behaviour; the operator can raise it (e.g. 50) so a low-score
    # candidate the manual modal would still display gets held back
    # from auto-dispatch. Manual grabs ignore this floor — the
    # operator explicitly chose the candidate.
    auto_grab_min_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    __table_args__ = (UniqueConstraint("name", name="uq_quality_profile_name"),)


class RegionProfile(Base, _ProfileMixin):
    __tablename__ = "region_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    priorities: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    allow_fallback_outside_priorities: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    exclude_regions: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )

    __table_args__ = (UniqueConstraint("name", name="uq_region_profile_name"),)


class DumpProfile(Base, _ProfileMixin):
    __tablename__ = "dump_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_dump_status: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    allow_proto_beta: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    allow_hacks: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    allow_trainers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    allow_translations: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    prefer_revision: Mapped[str] = mapped_column(
        String(8), nullable=False, default="latest"
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_dump_profile_name"),
        CheckConstraint(_PREFER_REVISION_CHECK, name="ck_dump_profile_prefer_revision"),
    )


class LanguageProfile(Base, _ProfileMixin):
    __tablename__ = "language_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    required_languages: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    preferred_languages: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    exclude_japanese_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    __table_args__ = (UniqueConstraint("name", name="uq_language_profile_name"),)


class NamingProfile(Base, _ProfileMixin):
    __tablename__ = "naming_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    convention: Mapped[str] = mapped_column(String(16), nullable=False)
    template: Mapped[str] = mapped_column(String, nullable=False)
    platform_subfolder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    replace_illegal_chars: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    multi_disc_subfolder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_naming_profile_name"),
        CheckConstraint(_NAMING_CONVENTION_CHECK, name="ck_naming_profile_convention"),
    )


class CustomFormat(Base, _ProfileMixin):
    __tablename__ = "custom_format"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    conditions: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    # Migration 0041 — enabled flag + source tracking.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    """When false, the pipeline ignores this CF when aggregating
    scores. Row stays in the table so the operator can flip it
    back on without losing the conditions."""
    source_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("pack_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    """FK to the community source that ingested this CF. NULL when
    the CF is either a built-in factory seed
    (``is_factory_default=true``) or operator-created via the UI
    (``is_factory_default=false``)."""

    __table_args__ = (
        UniqueConstraint("name", name="uq_custom_format_name"),
        CheckConstraint(_CUSTOM_FORMAT_SCORE_CHECK, name="ck_custom_format_score"),
    )


class LibraryCustomFormat(Base):
    """m2m linking libraries to custom formats.

    Created here with both columns + composite PK + FK on
    ``custom_format_id``. The FK on ``library_id`` is added by
    spec 009's migration once the ``library`` table exists.
    """

    __tablename__ = "library_custom_format"

    library_id: Mapped[int] = mapped_column(Integer, nullable=False)
    custom_format_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("custom_format.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "library_id", "custom_format_id", name="pk_library_custom_format"
        ),
    )


__all__ = [
    "CustomFormat",
    "DumpProfile",
    "LanguageProfile",
    "LibraryCustomFormat",
    "NamingProfile",
    "QualityProfile",
    "RegionProfile",
]
