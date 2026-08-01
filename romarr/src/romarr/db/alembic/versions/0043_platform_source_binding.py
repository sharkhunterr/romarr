"""Add ``platform.pack_source_id`` FK + ``platform_source_binding`` table.

Ships the *skip* half of the community-source conflict-resolution
model :

  * ``platform.pack_source_id`` — nullable FK to ``pack_sources.id``
    (ON DELETE SET NULL). Stamped on every insert / update from a
    community source so operators can trace "which pack put this
    row here". Existing rows land NULL and get backfilled on the
    next apply of any source touching their slug.
  * ``platform_source_binding`` — per-(source, slug) override
    table. ``mode='skip'`` tells the ingester to ignore a
    platform when that source's pack is applied. The ``mode``
    column is an enum with room for ``prefer`` / ``merge`` in
    Phase B.2 (per-slug scalar preference + array fusion), but
    only ``skip`` is honoured today.

Revision ID: 0043_platform_source_binding
Revises: 0042_preseed_official_platform_source
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0043_platform_source_binding"
down_revision: Union[str, Sequence[str], None] = (
    "0042_preseed_official_platform_source"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. platform.pack_source_id — provenance FK.
    with op.batch_alter_table("platform") as batch:
        batch.add_column(
            sa.Column("pack_source_id", sa.Integer(), nullable=True)
        )
        batch.create_foreign_key(
            "fk_platform_pack_source_id",
            "pack_sources",
            ["pack_source_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 2. platform_source_binding — per-(source, slug) override.
    op.create_table(
        "platform_source_binding",
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("platform_slug", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
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
        sa.PrimaryKeyConstraint(
            "source_id", "platform_slug", name="pk_platform_source_binding"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["pack_sources.id"],
            name="fk_platform_source_binding_source_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "mode IN ('skip','prefer','merge')",
            name="ck_platform_source_binding_mode",
        ),
    )
    op.create_index(
        "ix_platform_source_binding_slug",
        "platform_source_binding",
        ["platform_slug"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_source_binding_slug",
        table_name="platform_source_binding",
    )
    op.drop_table("platform_source_binding")
    with op.batch_alter_table("platform") as batch:
        batch.drop_constraint(
            "fk_platform_pack_source_id", type_="foreignkey"
        )
        batch.drop_column("pack_source_id")
