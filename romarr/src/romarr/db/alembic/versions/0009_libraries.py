"""Spec 009 — Library Management & Exporters schema.

Two new tables (``library``, ``library_platform``) plus one column
addition on the existing ``release`` table (``library_id`` with FK
to ``library(id) ON DELETE SET NULL``) plus the deferred FK on
``library_custom_format.library_id`` from spec 006.

This migration is the integrating one for forward-reference FKs:

  * Spec 006 declared ``library_custom_format.library_id`` as a
    column NOT NULL but without an FK target — the FK lands here.
  * Spec 008 (Import Pipeline), if shipped before this one, queues
    ``unidentified_dump.library_id`` as a column without an FK.
    This migration finalises that FK iff the column exists. If
    spec 008 ships AFTER this one, its own gated migration adds
    the FK and this branch no-ops.

Revision ID: 0009_libraries
Revises: 0007_search
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

revision = "0009_libraries"
down_revision = "0007_search"
branch_labels = None
depends_on = None


def _column_exists(bind: Connection, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _fk_exists(bind: Connection, table: str, fk_name: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table))


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "library",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column(
            "platform_subfolders",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "platforms_restricted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "quality_profile_id",
            sa.Integer(),
            sa.ForeignKey("quality_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "region_profile_id",
            sa.Integer(),
            sa.ForeignKey("region_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dump_profile_id",
            sa.Integer(),
            sa.ForeignKey("dump_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "language_profile_id",
            sa.Integer(),
            sa.ForeignKey("language_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "naming_profile_id",
            sa.Integer(),
            sa.ForeignKey("naming_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "monitored_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "use_hardlinks",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "lifecycle_policy",
            sa.String(32),
            nullable=False,
            server_default="hardlink_and_seed",
        ),
        sa.Column(
            "delete_after_import",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "keep_dump_history",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "min_disk_free_gb",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "preserve_archive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exporter_romm_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("exporter_romm_url", sa.String(512), nullable=True),
        sa.Column(
            "exporter_romm_api_key_encrypted", sa.LargeBinary(), nullable=True
        ),
        sa.Column(
            "exporter_esde_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exporter_pegasus_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exporter_launchbox_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exporter_launchbox_per_platform",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "scan_poll_seconds",
            sa.Integer(),
            nullable=False,
            server_default="3600",
        ),
        sa.Column(
            "heartbeat_seconds",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column(
            "last_full_scan_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_incremental_scan_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_scan_status", sa.String(16), nullable=True),
        sa.Column(
            "last_heartbeat_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_library_name"),
        sa.CheckConstraint(
            "lifecycle_policy IN "
            "('hardlink_and_seed','move_and_remove','copy_and_keep')",
            name="ck_library_lifecycle_policy",
        ),
        sa.CheckConstraint(
            "status IN ('ok','unavailable')",
            name="ck_library_status",
        ),
        sa.CheckConstraint(
            "last_scan_status IS NULL OR "
            "last_scan_status IN ('success','partial','failed')",
            name="ck_library_last_scan_status",
        ),
        sa.CheckConstraint("min_disk_free_gb >= 1", name="ck_library_min_disk_free"),
        sa.CheckConstraint("scan_poll_seconds >= 60", name="ck_library_scan_poll"),
        sa.CheckConstraint("heartbeat_seconds >= 5", name="ck_library_heartbeat"),
    )
    op.create_index("idx_library_status", "library", ["status"])

    op.create_table(
        "library_platform",
        sa.Column(
            "library_id",
            sa.Integer(),
            sa.ForeignKey("library.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "library_id", "platform_id", name="pk_library_platform"
        ),
    )

    # release.library_id — column + FK
    with op.batch_alter_table("release") as batch_op:
        batch_op.add_column(sa.Column("library_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_release_library_id",
            "library",
            ["library_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("idx_release_library_id", ["library_id"])

    # library_custom_format.library_id FK — spec 006 created the column
    # NOT NULL but without an FK target; finalise it here.
    if not _fk_exists(
        bind, "library_custom_format", "fk_library_custom_format_library"
    ):
        with op.batch_alter_table("library_custom_format") as batch_op:
            batch_op.create_foreign_key(
                "fk_library_custom_format_library",
                "library",
                ["library_id"],
                ["id"],
                ondelete="CASCADE",
            )

    # unidentified_dump.library_id FK — only finalise if spec 008 has
    # already shipped its column without the FK. If spec 008 lands
    # after this migration, its own migration adds the FK directly.
    if _column_exists(
        bind, "unidentified_dump", "library_id"
    ) and not _fk_exists(bind, "unidentified_dump", "fk_unidentified_dump_library"):
        with op.batch_alter_table("unidentified_dump") as batch_op:
            batch_op.create_foreign_key(
                "fk_unidentified_dump_library",
                "library",
                ["library_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()

    if _fk_exists(bind, "unidentified_dump", "fk_unidentified_dump_library"):
        with op.batch_alter_table("unidentified_dump") as batch_op:
            batch_op.drop_constraint(
                "fk_unidentified_dump_library", type_="foreignkey"
            )

    if _fk_exists(
        bind, "library_custom_format", "fk_library_custom_format_library"
    ):
        with op.batch_alter_table("library_custom_format") as batch_op:
            batch_op.drop_constraint(
                "fk_library_custom_format_library", type_="foreignkey"
            )

    with op.batch_alter_table("release") as batch_op:
        batch_op.drop_index("idx_release_library_id")
        batch_op.drop_constraint("fk_release_library_id", type_="foreignkey")
        batch_op.drop_column("library_id")

    op.drop_table("library_platform")
    op.drop_index("idx_library_status", table_name="library")
    op.drop_table("library")
