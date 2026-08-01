"""Snapshot per-source contributions per slug + global source rank.

Ships the ``prefer`` half of the conflict-resolution matrix and
the array-fusion behaviour :

  * ``platform_source_contribution`` — one row per
    (source_id, platform_slug), storing the full snapshot of what
    that source contributed the last time it applied. Materialize
    reads the stack, applies bindings, and rewrites the live
    ``platform`` row from the aggregate.
  * ``platform_pack_config.source_order`` — JSON list of source
    IDs in preferred order (highest priority first). Sources not
    listed rank below listed ones, ordered by id. Consulted only
    when no ``prefer`` binding wins the scalar vote for a slug.

Revision ID: 0044_platform_source_contribution
Revises: 0043_platform_source_binding
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044_platform_source_contribution"
down_revision: Union[str, Sequence[str], None] = (
    "0043_platform_source_binding"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_source_contribution",
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("platform_slug", sa.String(length=64), nullable=False),
        sa.Column("contribution", sa.JSON(), nullable=False),
        sa.Column("pack_version", sa.String(length=64), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "source_id",
            "platform_slug",
            name="pk_platform_source_contribution",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["pack_sources.id"],
            name="fk_platform_source_contribution_source_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_platform_source_contribution_slug",
        "platform_source_contribution",
        ["platform_slug"],
    )

    with op.batch_alter_table("platform_pack_config") as batch:
        batch.add_column(
            sa.Column(
                "source_order",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("platform_pack_config") as batch:
        batch.drop_column("source_order")

    op.drop_index(
        "ix_platform_source_contribution_slug",
        table_name="platform_source_contribution",
    )
    op.drop_table("platform_source_contribution")
