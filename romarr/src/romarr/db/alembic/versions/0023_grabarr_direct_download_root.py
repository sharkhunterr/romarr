"""Slice 427 / R3a — add ``download_client.download_root``.

The Grabarr-direct streamer (slice 425) needs a base directory
under which to write ``http_direct`` files. Until this slice it
read the value from the ``ROMARR_GRABARR_DIRECT_DOWNLOAD_ROOT``
env var (default ``/downloads``); the new column lets operators
pin it per-row from the "Add Grabarr" wizard so a single Romarr
deploy can drive multiple Grabarr instances each landing in their
own subtree.

Nullable on purpose: only ``type='grabarr_direct'`` rows fill it
in. qBit / SAB / the v1-deferred stubs (Transmission, Deluge,
NZBGet) leave it NULL — qBit owns its own download paths via its
own config; SAB the same. No CHECK because the column is purely
informational from the routing engine's POV.

Revision ID: 0023_grabarr_direct_download_root
Revises: 0022_grabarr_direct_foundation
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0023_grabarr_direct_download_root"
down_revision = "0022_grabarr_direct_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("download_client") as batch_op:
        batch_op.add_column(
            sa.Column("download_root", sa.String(length=512), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("download_client") as batch_op:
        batch_op.drop_column("download_root")
