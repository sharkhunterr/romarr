"""SQLAlchemy models for the platform-packs feature.

Two new tables:

  - ``parsing_strategies`` — pack-defined regex templates referenced
    by platform formats (FR-014a).
  - ``platform_pack_application_log`` — append-only audit trail of
    every pack-application attempt (FR-023, FR-024).
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
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_PACK_SOURCE_VALUES = ("builtin", "community", "user")
_PACK_SOURCE_CHECK = (
    "pack_source IN ("
    + ",".join(f"'{v}'" for v in _PACK_SOURCE_VALUES)
    + ")"
)

_ACTION_VALUES = ("applied", "reapplied", "skipped", "failed")
_ACTION_CHECK = "action IN (" + ",".join(f"'{v}'" for v in _ACTION_VALUES) + ")"

_STATUS_VALUES = ("success", "failed")
_STATUS_CHECK = "status IN (" + ",".join(f"'{v}'" for v in _STATUS_VALUES) + ")"


class ParsingStrategy(Base, TimestampMixin):
    """Pack-defined regex template referenced by platform formats."""

    __tablename__ = "parsing_strategies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    apply_to_platforms: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    pack_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pack_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="builtin"
    )

    __table_args__ = (
        CheckConstraint(_PACK_SOURCE_CHECK, name="ck_parsing_strategy_pack_source"),
    )


class PlatformPackApplicationLog(Base):
    """Audit trail row for every pack-apply attempt."""

    __tablename__ = "platform_pack_application_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Intentionally NOT a FK to ``platform_pack.pack_version``: failed
    # runs MUST persist their audit row even though the data-side
    # transaction (which would have inserted the matching pack row)
    # rolled back (FR-024). The pack_version is a logical pointer for
    # human auditors, not a referential-integrity constraint.
    pack_version: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    platforms_affected: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    parsing_strategies_affected: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    applied_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index(
            "idx_platform_pack_application_log_pack_version", "pack_version"
        ),
        Index(
            "idx_platform_pack_application_log_started_at",
            "started_at",
        ),
        CheckConstraint(_ACTION_CHECK, name="ck_pp_application_log_action"),
        CheckConstraint(_STATUS_CHECK, name="ck_pp_application_log_status"),
    )


_SOURCE_KIND_VALUES = ("raw", "github_dir")
_SOURCE_KIND_CHECK = (
    "kind IN (" + ",".join(f"'{v}'" for v in _SOURCE_KIND_VALUES) + ")"
)

_LAST_STATUS_VALUES = ("ok", "partial", "error")
_LAST_STATUS_CHECK = (
    "last_status IS NULL OR last_status IN ("
    + ",".join(f"'{v}'" for v in _LAST_STATUS_VALUES)
    + ")"
)

# Migration 0040 — the ``pack_sources`` table generalised to
# host every community-source kind (platform packs, custom
# formats, more later). ``resource_type`` is the discriminator.
_RESOURCE_TYPE_VALUES = ("platform_pack", "custom_format")

_TRUST_STATUS_VALUES = ("pending", "trusted")

_PRIORITY_VALUES = ("builtin", "community")
_PRIORITY_CHECK = (
    "priority IN (" + ",".join(f"'{v}'" for v in _PRIORITY_VALUES) + ")"
)


class PlatformPackConfig(Base, TimestampMixin):
    """Singleton row driving the platform-pack subsystem.

    ``builtin_enabled`` gates the boot-time auto-apply of the wheel-bundled
    builtin pack. ``priority`` decides which side wins when the same slug
    lives in both the builtin and a community source:

      * ``"community"`` — natural apply order (builtin at boot, community
        on sync) means community's later apply wins the shared slugs.
      * ``"builtin"`` — after every community sync we re-apply the builtin
        so builtin values overwrite whatever the community pack wrote for
        overlapping slugs. Slugs the builtin doesn't touch stay as-is.

    Exactly one row (``id = 1``); the API get-or-creates it.
    """

    __tablename__ = "platform_pack_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    builtin_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="community"
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_platform_pack_config_singleton"),
        CheckConstraint(_PRIORITY_CHECK, name="ck_platform_pack_config_priority"),
    )


class PackSource(Base, TimestampMixin):
    """Remote community source (typically a GitHub URL).

    Row stores one URL the operator has registered; the Update
    Center syncs from it periodically and tracks whether a new
    version is available.

    ``resource_type`` is the discriminator introduced by migration
    0040 — ``platform_pack`` covers the original YAML-directory
    format, ``custom_format`` covers the manifest-based JSON packs
    the Update Center added. Adapters per resource_type handle the
    parse / validate / apply pipeline.

    ``kind`` distinguishes the URL shape :
      * ``raw`` — the URL points directly at a single body file
        (``raw.githubusercontent.com/...``, or any HTTPS resource).
      * ``github_dir`` — the URL points at a GitHub directory; the
        sync walks it and ingests every child that matches the
        adapter's file convention.

    ``last_seen_version`` / ``installed_version`` — the two halves
    the Update Center badge reads. A source with
    ``last_seen_version != installed_version`` (and both non-null)
    contributes to the "N mises à jour" counter.

    ``trust_status`` — ``pending`` for a newly added source that
    hasn't had its manifest previewed / accepted yet, ``trusted``
    after the operator's first apply. Sync fetches happen either way
    (they're read-only); apply is blocked while ``pending``.
    """

    __tablename__ = "pack_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="platform_pack"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    trust_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="trusted"
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_applied_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_seen_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    installed_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_pack_sources_name"),
        CheckConstraint(_SOURCE_KIND_CHECK, name="ck_pack_sources_kind"),
        CheckConstraint(_LAST_STATUS_CHECK, name="ck_pack_sources_last_status"),
        CheckConstraint(
            "resource_type IN ("
            + ",".join(f"'{v}'" for v in _RESOURCE_TYPE_VALUES)
            + ")",
            name="ck_pack_sources_resource_type",
        ),
        CheckConstraint(
            "trust_status IN ("
            + ",".join(f"'{v}'" for v in _TRUST_STATUS_VALUES)
            + ")",
            name="ck_pack_sources_trust_status",
        ),
    )


_BINDING_MODE_VALUES = ("skip", "prefer", "merge")


class PlatformSourceBinding(Base, TimestampMixin):
    """Per-(source, slug) override for community platform packs.

    Introduced by migration 0043. Today only ``mode='skip'`` is
    honoured by the ingester — the ``prefer`` / ``merge`` modes are
    reserved for the follow-up slice that stores per-source snapshots
    and materialises the platform row from a rank-ordered aggregate.

    Semantics :

      * ``skip`` — this source's contribution for ``platform_slug``
        is ignored at ingest time. The platform stays as it was
        (from another source, or absent if this was the only source
        touching it).
      * ``prefer`` *(reserved)* — this source wins scalars for the
        slug even if another source is newer.
      * ``merge`` *(reserved)* — union-merge list fields across
        every source that touched the slug.
    """

    __tablename__ = "platform_source_binding"

    source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pack_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    platform_slug: Mapped[str] = mapped_column(
        String(64), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "mode IN ("
            + ",".join(f"'{v}'" for v in _BINDING_MODE_VALUES)
            + ")",
            name="ck_platform_source_binding_mode",
        ),
        Index(
            "ix_platform_source_binding_slug", "platform_slug"
        ),
    )


# Re-export for convenience in tests/code.
__all__: list[Any] = [
    "PackSource",
    "ParsingStrategy",
    "PlatformPackApplicationLog",
    "PlatformPackConfig",
    "PlatformSourceBinding",
]
