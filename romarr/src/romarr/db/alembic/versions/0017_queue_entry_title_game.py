"""Slice 367 — give ``queue_entry`` an operator-readable title + game.

Without these fields the Activity → Queue tab rendered each
row's ``download_client_native_id`` (info-hash for qBit, nzo_id
for SAB) as the line item, which reads like a 40-char hex
slug. Operators couldn't tell which release was which and the
parent game was completely invisible.

Adds:

  * ``title``   — the torrent / NZB title from the grab payload
                  (or whatever we last polled from the client).
                  TEXT NULL so legacy rows + watcher inserts that
                  don't know it yet stay valid.
  * ``game_id`` — FK → game.id ON DELETE SET NULL. Filled by the
                  manual-grab path immediately; the queue list UI
                  joins on this to show the parent game name.

Revision ID: 0017_queue_entry_title_game
Revises: 0016_queue_entry_release_nullable
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_queue_entry_title_game"
down_revision = "0016_queue_entry_release_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("queue_entry") as batch:
        batch.add_column(sa.Column("title", sa.String(), nullable=True))
        batch.add_column(
            sa.Column(
                "game_id",
                sa.Integer(),
                sa.ForeignKey("game.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.create_index("idx_queue_entry_game", ["game_id"])


def downgrade() -> None:
    with op.batch_alter_table("queue_entry") as batch:
        batch.drop_index("idx_queue_entry_game")
        batch.drop_column("game_id")
        batch.drop_column("title")
