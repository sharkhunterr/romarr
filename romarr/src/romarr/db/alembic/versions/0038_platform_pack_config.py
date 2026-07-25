"""Add ``platform_pack_config`` singleton — builtin toggle + priority.

Slice: platform pack config surface. One row, two knobs:

  - ``builtin_enabled`` — skip the boot-time auto-apply of the
    wheel-bundled builtin pack when False.
  - ``priority`` — ``"builtin"`` or ``"community"``. Drives whether
    a community sync gets its values overwritten by a re-apply of
    the builtin pack at the end of the sweep.

Revision ID: 0038_platform_pack_config
Revises: 0037_pack_sources
Create Date: 2026-07-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_platform_pack_config"
down_revision: Union[str, Sequence[str], None] = "0037_pack_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_pack_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "builtin_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "priority",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'community'"),
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
        sa.CheckConstraint("id = 1", name="ck_platform_pack_config_singleton"),
        sa.CheckConstraint(
            "priority IN ('builtin','community')",
            name="ck_platform_pack_config_priority",
        ),
    )


def downgrade() -> None:
    op.drop_table("platform_pack_config")
