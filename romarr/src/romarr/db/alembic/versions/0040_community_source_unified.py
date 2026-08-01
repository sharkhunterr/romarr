"""Generalise ``pack_sources`` into a unified community-source table.

Extends the existing table with the columns the unified Update
Center needs:

  * ``resource_type`` — discriminator (``platform_pack`` today,
    ``custom_format`` next, more later). Existing rows are backfilled
    to ``platform_pack`` since that's exactly what they hold.
  * ``last_seen_version`` / ``installed_version`` — the two halves
    of "update available" the badge reads. Nullable — a source that
    was never checked / never applied stays null.
  * ``auto_check`` — per-source override on the scheduler sweep.
    Defaults to true.
  * ``trust_status`` — ``pending`` for a newly added source that
    hasn't been previewed yet, ``trusted`` after operator OK. Existing
    rows are trusted (they were added under the old UI, no consent
    to migrate).

The old columns (``kind``, ``last_status``, ``last_error``,
``last_applied_count``) stay untouched so the existing platform-pack
API keeps working while the unified engine lands.

Revision ID: 0040_community_source_unified
Revises: 0039_download_client_path_mapping
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0040_community_source_unified"
down_revision: Union[str, Sequence[str], None] = (
    "0039_download_client_path_mapping"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_RESOURCE_TYPE_VALUES = ("platform_pack", "custom_format")
_RESOURCE_TYPE_CHECK = (
    "resource_type IN ("
    + ",".join(f"'{v}'" for v in _RESOURCE_TYPE_VALUES)
    + ")"
)

_TRUST_STATUS_VALUES = ("pending", "trusted")
_TRUST_STATUS_CHECK = (
    "trust_status IN ("
    + ",".join(f"'{v}'" for v in _TRUST_STATUS_VALUES)
    + ")"
)


def upgrade() -> None:
    # SQLite doesn't support adding a NOT NULL column without a
    # default in an ALTER, so we add each column nullable, backfill,
    # then tighten the constraint via batch mode.
    with op.batch_alter_table("pack_sources", recreate="auto") as batch:
        batch.add_column(
            sa.Column("resource_type", sa.String(length=32), nullable=True)
        )
        batch.add_column(
            sa.Column("last_seen_version", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("installed_version", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "auto_check",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch.add_column(
            sa.Column(
                "trust_status",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'trusted'"),
            )
        )

    # Backfill existing rows: they all hold platform packs.
    op.execute(
        "UPDATE pack_sources SET resource_type = 'platform_pack' "
        "WHERE resource_type IS NULL"
    )

    with op.batch_alter_table("pack_sources") as batch:
        batch.alter_column(
            "resource_type",
            existing_type=sa.String(length=32),
            nullable=False,
        )
        batch.create_check_constraint(
            "ck_pack_sources_resource_type", _RESOURCE_TYPE_CHECK
        )
        batch.create_check_constraint(
            "ck_pack_sources_trust_status", _TRUST_STATUS_CHECK
        )


def downgrade() -> None:
    with op.batch_alter_table("pack_sources") as batch:
        batch.drop_constraint(
            "ck_pack_sources_trust_status", type_="check"
        )
        batch.drop_constraint(
            "ck_pack_sources_resource_type", type_="check"
        )
        batch.drop_column("trust_status")
        batch.drop_column("auto_check")
        batch.drop_column("installed_version")
        batch.drop_column("last_seen_version")
        batch.drop_column("resource_type")
