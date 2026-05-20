"""Slice 465 — make ``queue_entry.download_client_id`` nullable.

URL-sourced ROM content packs don't come from a download client
— Romarr streams the archive itself — but the operator still
wants to watch the transfer in Activity → Queue like a normal
grab. Relaxing the FK lets a *Romarr-internal* download mirror
itself into ``queue_entry`` with ``download_client_id = NULL``
and a synthetic ``download_client_native_id`` (e.g.
``rom_pack:42``).

The reconciler groups active rows by client id and polls each
client; rows with a NULL client are skipped — they have no
client to poll, their progress is driven by the ROM-pack ingest
pipeline instead.

The unique ``(download_client_id, native_id)`` constraint still
holds: NULL client ids don't collide under SQL NULL semantics,
and the synthetic native id is unique per pack.

Revision ID: 0031_queue_entry_internal_downloads
Revises: 0030_rom_pack_config
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_queue_entry_internal_downloads"
down_revision = "0030_rom_pack_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite-safe: ``batch_alter_table`` rebuilds the table to
    # alter the column nullability + preserve indexes / FKs.
    with op.batch_alter_table("queue_entry") as batch:
        batch.alter_column(
            "download_client_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    # Refuse to re-tighten if any Romarr-internal rows exist —
    # there's no client id to backfill them with.
    bind = op.get_bind()
    orphan = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM queue_entry "
            "WHERE download_client_id IS NULL"
        )
    ).scalar()
    if orphan and orphan > 0:
        raise RuntimeError(
            f"queue_entry has {orphan} rows with NULL download_client_id; "
            "cannot downgrade without losing them."
        )
    with op.batch_alter_table("queue_entry") as batch:
        batch.alter_column(
            "download_client_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
