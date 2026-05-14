"""Slice 454 — add ``queue_entry.content_path`` + ``import_attempted_at``.

The grabarr-direct download client tracks in-flight + completed
transfers in an **in-memory** ``_pending`` dict. A container
restart between "download completed" and "watcher dispatched
the import" wipes that dict — ``list_managed_downloads()``
returns empty, the watcher has nothing to pick up, and the
``queue_entry`` row sits at ``state='completed'`` forever with
the file orphaned on disk.

Two new columns make the queue row self-sufficient:

- ``content_path`` — where the finished file landed on disk.
  The reconciler persists ``DownloadStatus.save_path`` here on
  every poll, so by the time a download reaches ``completed``
  the path is durable.
- ``import_attempted_at`` — set by the recovery dispatch the
  first time it hands a completed row to ``run_import``. NULL
  means "completed but never imported" — exactly the rows the
  reconciler's recovery pass needs to find after a restart.

Both nullable; existing rows backfill to NULL and the recovery
pass simply skips any completed row whose ``content_path`` it
never managed to capture (small window — the reconciler ticks
every 30 s).

Revision ID: 0027_queue_entry_content_path
Revises: 0026_dat_source_table
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0027_queue_entry_content_path"
down_revision = "0026_dat_source_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("queue_entry") as batch_op:
        batch_op.add_column(
            sa.Column("content_path", sa.String(length=1024), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "import_attempted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("queue_entry") as batch_op:
        batch_op.drop_column("import_attempted_at")
        batch_op.drop_column("content_path")
