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


class PackSource(Base, TimestampMixin):
    """Remote source (typically a GitHub URL) that ships one or more
    platform-pack YAML bodies.

    Two ``kind``s :
      * ``raw`` — the URL points directly at a single YAML file
        (``raw.githubusercontent.com/...``, or any HTTPS ``*.yaml``).
      * ``github_dir`` — the URL points at a GitHub directory; the
        sync walks it and ingests every ``*.yaml`` / ``*.yml`` child.

    ``kind`` is auto-detected at add-time via
    :func:`romarr.platform_packs.remote.classify_url` and can be
    overridden by the client if the heuristic misfires.
    """

    __tablename__ = "pack_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_applied_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_pack_sources_name"),
        CheckConstraint(_SOURCE_KIND_CHECK, name="ck_pack_sources_kind"),
        CheckConstraint(_LAST_STATUS_CHECK, name="ck_pack_sources_last_status"),
    )


# Re-export for convenience in tests/code.
__all__: list[Any] = [
    "PackSource",
    "ParsingStrategy",
    "PlatformPackApplicationLog",
]
