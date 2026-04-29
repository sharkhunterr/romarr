"""Spec 003 — Platform Packs schema.

Creates two new tables:
  - ``parsing_strategies``               (FR-014a)
  - ``platform_pack_application_log``    (FR-023, FR-024)

The ``platform_pack`` table from foundation already carries
``contents_hash`` so this migration does NOT need to add it. Spec 003
sits cleanly atop spec 002 and spec 010 — the linear chain is:

    0001_initial_schema → 0010_auth_multiuser → 0002_metadata_layer → 0003_platform_packs

Revision ID: 0003_platform_packs
Revises: 0002_metadata_layer
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_platform_packs"
down_revision = "0002_metadata_layer"
branch_labels = None
depends_on = None


_PACK_SOURCE_CHECK = "pack_source IN ('builtin','community','user')"
_ACTION_CHECK = "action IN ('applied','reapplied','skipped','failed')"
_STATUS_CHECK = "status IN ('success','failed')"


def upgrade() -> None:
    op.create_table(
        "parsing_strategies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column(
            "apply_to_platforms",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("pack_version", sa.String(16), nullable=True),
        sa.Column(
            "pack_source",
            sa.String(16),
            nullable=False,
            server_default="builtin",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            _PACK_SOURCE_CHECK, name="ck_parsing_strategy_pack_source"
        ),
    )

    op.create_table(
        "platform_pack_application_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pack_version",
            sa.String(16),
            sa.ForeignKey("platform_pack.pack_version", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column(
            "platforms_affected",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "parsing_strategies_affected",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("applied_by", sa.String(128), nullable=True),
        sa.CheckConstraint(_ACTION_CHECK, name="ck_pp_application_log_action"),
        sa.CheckConstraint(_STATUS_CHECK, name="ck_pp_application_log_status"),
    )
    op.create_index(
        "idx_platform_pack_application_log_pack_version",
        "platform_pack_application_log",
        ["pack_version"],
    )
    op.create_index(
        "idx_platform_pack_application_log_started_at",
        "platform_pack_application_log",
        ["started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_platform_pack_application_log_started_at",
        table_name="platform_pack_application_log",
    )
    op.drop_index(
        "idx_platform_pack_application_log_pack_version",
        table_name="platform_pack_application_log",
    )
    op.drop_table("platform_pack_application_log")
    op.drop_table("parsing_strategies")
