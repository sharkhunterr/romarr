"""SQLAlchemy models for the libraries feature (spec 009).

Two tables — ``library`` (core entity) and ``library_platform``
(many-to-many platform allowlist) — plus one column addition on
the existing ``release`` table (``library_id``, owned by the
domain model).

The five profile FK columns on ``library`` are the contract: per
data-model.md they are NOT NULL with ``ON DELETE RESTRICT``. Spec
006's force-delete protection is the constitutional counterpart;
together they guarantee a library cannot orphan its profiles.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_LIFECYCLE_CHECK = (
    "lifecycle_policy IN ('hardlink_and_seed','move_and_remove','copy_and_keep')"
)
_STATUS_CHECK = "status IN ('ok','unavailable')"
_LAST_SCAN_STATUS_CHECK = (
    "last_scan_status IS NULL OR last_scan_status IN ('success','partial','failed')"
)


class Library(Base, TimestampMixin):
    """The operator's "where my ROMs live" entity.

    Each library carries its own five profile bindings, its own
    lifecycle policy, its own optional platform allowlist (via the
    ``library_platform`` m2m), and its own per-exporter switches.
    """

    __tablename__ = "library"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)

    platform_subfolders: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    platforms_restricted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    quality_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("quality_profile.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    region_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("region_profile.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    dump_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dump_profile.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    language_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("language_profile.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    naming_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("naming_profile.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    monitored_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    use_hardlinks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lifecycle_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="hardlink_and_seed"
    )
    delete_after_import: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    keep_dump_history: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    min_disk_free_gb: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    preserve_archive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    exporter_romm_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    exporter_romm_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    exporter_romm_api_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    exporter_esde_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    exporter_pegasus_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    exporter_launchbox_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    exporter_launchbox_per_platform: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    scan_poll_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600
    )
    heartbeat_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    last_full_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_incremental_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_scan_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_library_name"),
        CheckConstraint(_LIFECYCLE_CHECK, name="ck_library_lifecycle_policy"),
        CheckConstraint(_STATUS_CHECK, name="ck_library_status"),
        CheckConstraint(_LAST_SCAN_STATUS_CHECK, name="ck_library_last_scan_status"),
        CheckConstraint("min_disk_free_gb >= 1", name="ck_library_min_disk_free"),
        CheckConstraint("scan_poll_seconds >= 60", name="ck_library_scan_poll"),
        CheckConstraint("heartbeat_seconds >= 5", name="ck_library_heartbeat"),
    )


class LibraryPlatform(Base, TimestampMixin):
    """Many-to-many platform allowlist for a library.

    Empty m2m + ``library.platforms_restricted = false`` means the
    library accepts any platform. Empty m2m +
    ``platforms_restricted = true`` is rejected at validation
    (FR-005).
    """

    __tablename__ = "library_platform"

    library_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("library.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "library_id", "platform_id", name="pk_library_platform"
        ),
    )


# Re-export BigInteger so future modules importing constraint helpers
# from this file find a consistent vocabulary even if SQLAlchemy moves
# things around between minor versions.
__all__ = ["BigInteger", "Library", "LibraryPlatform"]
