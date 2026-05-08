"""Slice 362 — make ``queue_entry.release_id`` nullable.

Manual grabs from a game-level search modal don't have a Release
yet (the importer creates one when the file lands). Until this
slice the grab couldn't mirror itself into ``queue_entry``
because the FK was NOT NULL — so the Activity → Queue tab
stayed empty even though qBit was happily downloading. Relax
the constraint so the row can be inserted with the parent
``game_id`` carried alongside; the future poll-loop will fill
``release_id`` once the importer resolves it.

The unique ``(download_client_id, native_id)`` constraint is
preserved verbatim — that's the operator-visible identity.

Revision ID: 0016_queue_entry_release_nullable
Revises: 0015_exporter_runs
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_queue_entry_release_nullable"
down_revision = "0015_exporter_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite-safe: ``batch_alter_table`` rebuilds the table to
    # alter the column nullability + preserve indexes.
    with op.batch_alter_table("queue_entry") as batch:
        batch.alter_column(
            "release_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    # Coerce orphan rows to a sentinel before re-tightening — but
    # we don't ship a sentinel id, so the only safe downgrade is
    # to refuse if any orphan row exists.
    bind = op.get_bind()
    orphan = bind.execute(
        sa.text("SELECT COUNT(*) FROM queue_entry WHERE release_id IS NULL")
    ).scalar()
    if orphan and orphan > 0:
        raise RuntimeError(
            f"queue_entry has {orphan} rows with NULL release_id; "
            "cannot downgrade without losing them."
        )
    with op.batch_alter_table("queue_entry") as batch:
        batch.alter_column(
            "release_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
