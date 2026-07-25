"""Add ``pack_sources`` table — remote (GitHub) platform-pack sources.

Enables the operator to register one or more GitHub URLs (raw YAML
files or directory listings) as trusted platform-pack sources and
sync from them on demand instead of manually uploading each YAML.

Revision ID: 0037_pack_sources
Revises: 0036_import_history_size_bytes
Create Date: 2026-07-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_pack_sources"
down_revision: Union[str, Sequence[str], None] = "0036_import_history_size_bytes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pack_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=16), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "last_applied_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("name", name="uq_pack_sources_name"),
        sa.CheckConstraint(
            "kind IN ('raw','github_dir')", name="ck_pack_sources_kind"
        ),
        sa.CheckConstraint(
            "last_status IS NULL OR last_status IN ('ok','partial','error')",
            name="ck_pack_sources_last_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("pack_sources")
