"""Slice 432 — add ``indexer.enabled`` master switch.

Pre-slice operators could only toggle the three per-feature
capability flags (``enable_rss`` / ``enable_automatic_search`` /
``enable_interactive_search``); disabling the whole indexer meant
flipping all three off one at a time. The new ``enabled`` column
is a single kill-switch — when False the registry's
``load_enabled`` skips the row entirely so search rounds, RSS
poll, manual grab, and dispatch all see one row fewer without
having to zero out the capability toggles.

Default True so every existing row stays in active rotation —
operators only opt out when they explicitly disable a row from
the Settings → Indexers chip.

Revision ID: 0024_indexer_enabled_master_switch
Revises: 0023_grabarr_direct_download_root
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0024_indexer_enabled_master_switch"
down_revision = "0023_grabarr_direct_download_root"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("indexer") as batch_op:
        batch_op.add_column(
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("indexer") as batch_op:
        batch_op.drop_column("enabled")
