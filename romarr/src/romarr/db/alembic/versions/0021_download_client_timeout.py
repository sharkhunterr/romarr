"""Slice 420 — add ``download_client.timeout_seconds``.

Per-client HTTP timeout used for every qBit / SAB API call AND
for the in-band ``/download`` URL fetch we do during torrent add
when an indexer proxies through a slow upstream. Hard-coded 15 s
in slice 416 was failing operators running Prowlarr against
Grabarr where the upstream returns past that bound (we observed
``duration_ms=15019`` failures on the manual-grab path).

Range 5..600 s, default 60 s — generous default so existing
rows post-upgrade still feel snappy for healthy clients but
absorb the Grabarr worst case after an operator bumps it from
the Settings → Download Clients form.

Revision ID: 0021_download_client_timeout
Revises: 0020_indexer_timeout_range
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0021_download_client_timeout"
down_revision = "0020_indexer_timeout_range"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("download_client") as batch_op:
        batch_op.add_column(
            sa.Column(
                "timeout_seconds",
                sa.Integer(),
                nullable=False,
                server_default="60",
            )
        )
        batch_op.create_check_constraint(
            "ck_download_client_timeout_range",
            "timeout_seconds BETWEEN 5 AND 600",
        )


def downgrade() -> None:
    with op.batch_alter_table("download_client") as batch_op:
        batch_op.drop_constraint(
            "ck_download_client_timeout_range", type_="check"
        )
        batch_op.drop_column("timeout_seconds")
