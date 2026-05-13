"""Slice 443 — persist DAT source URLs in their own table.

Pre-slice the only DAT-related table was ``dat_entry`` — the
**parsed entries cache**. The list of URLs to fetch (no-intro
mirror for PSX, redump for PS2, etc.) lived nowhere; the
``DatUpdateRunner`` accepted ``DatSourceSpec`` triples passed in
by the caller but no persistence layer existed.

This table closes the gap: operators (and the bootstrap helper
that seeds recommended URLs at first boot) write rows here, the
update runner reads them on its scheduled tick + on manual
``POST /dat-source/{id}/refresh`` calls. Each row tracks the
last refresh outcome so the Settings → DAT Sources page can
show success / failure / entry-count at a glance.

Revision ID: 0026_dat_source_table
Revises: 0025_import_history_download_failed
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0026_dat_source_table"
down_revision = "0025_import_history_download_failed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dat_source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "last_refresh_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_refresh_status", sa.String(length=16), nullable=True
        ),
        sa.Column("last_refresh_error", sa.String(length=500), nullable=True),
        sa.Column("last_entry_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint(
            "source", "platform_id", name="uq_dat_source_source_platform"
        ),
        sa.CheckConstraint(
            "source IN ('no-intro','redump','tosec','goodtools','hasheous',"
            "'playmatch','custom')",
            name="ck_dat_source_source",
        ),
        sa.CheckConstraint(
            "last_refresh_status IS NULL "
            "OR last_refresh_status IN ('ok','failed','running')",
            name="ck_dat_source_status",
        ),
    )
    op.create_index(
        "ix_dat_source_platform_id", "dat_source", ["platform_id"]
    )
    op.create_index("ix_dat_source_enabled", "dat_source", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_dat_source_enabled", table_name="dat_source")
    op.drop_index("ix_dat_source_platform_id", table_name="dat_source")
    op.drop_table("dat_source")
