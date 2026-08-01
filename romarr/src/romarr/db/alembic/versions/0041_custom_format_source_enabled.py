"""Add ``enabled`` + ``source_id`` columns to ``custom_format``.

Two new capabilities the Custom Formats page surfaces after the
Update Center lands:

  * ``enabled`` (bool, default True) — operator can flip a CF off
    without deleting it. The pipeline skips disabled CFs when
    aggregating scores.
  * ``source_id`` (int, nullable FK → pack_sources.id) — tracks
    where a CF came from : NULL + is_factory_default=true ⇒
    built-in seed; NULL + is_factory_default=false ⇒ operator-
    created via the UI; NOT NULL ⇒ community pack (joinable to
    pack_sources.name for display).

Revision ID: 0041_custom_format_source_enabled
Revises: 0040_community_source_unified
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041_custom_format_source_enabled"
down_revision: Union[str, Sequence[str], None] = "0040_community_source_unified"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("custom_format", recreate="auto") as batch:
        batch.add_column(
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch.add_column(
            sa.Column("source_id", sa.Integer(), nullable=True)
        )
        batch.create_foreign_key(
            "fk_custom_format_source_id",
            "pack_sources",
            ["source_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("custom_format") as batch:
        batch.drop_constraint("fk_custom_format_source_id", type_="foreignkey")
        batch.drop_column("source_id")
        batch.drop_column("enabled")
