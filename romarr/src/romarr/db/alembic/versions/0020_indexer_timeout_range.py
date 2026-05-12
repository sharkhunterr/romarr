"""Slice 419 — widen ``indexer.timeout_seconds`` upper bound to 600 s.

Operators running Prowlarr against Grabarr (or any indexer that
proxies a slow upstream) hit search responses past the previous
120 s cap. Raise the CHECK constraint to 600 s (10 minutes) so
the Add / Edit Indexer form's new ``timeout_seconds`` input
accepts the realistic worst-case waits.

Revision ID: 0020_indexer_timeout_range
Revises: 0019_platform_aliases
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op


revision = "0020_indexer_timeout_range"
down_revision = "0019_platform_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("indexer") as batch_op:
        batch_op.drop_constraint(
            "ck_indexer_timeout_range", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_indexer_timeout_range",
            "timeout_seconds BETWEEN 5 AND 600",
        )


def downgrade() -> None:
    # Clamp any rows above the old ceiling before re-tightening so
    # the recreate doesn't fail on existing data.
    op.execute(
        "UPDATE indexer SET timeout_seconds = 120 "
        "WHERE timeout_seconds > 120"
    )
    with op.batch_alter_table("indexer") as batch_op:
        batch_op.drop_constraint(
            "ck_indexer_timeout_range", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_indexer_timeout_range",
            "timeout_seconds BETWEEN 5 AND 120",
        )
