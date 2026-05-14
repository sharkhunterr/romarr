"""Slice 385 — Sonarr-style library binding on Game.

Adds:

  * ``game.library_id`` — nullable FK to ``library.id`` so a Game
    knows which library it belongs to. The operator picks the
    library at add-time (the AddGame modal), the importer reads
    it back when auto-creating a Release for a manual grab so
    the file lands under the right library root with that
    library's profile cascade applied.

Backward-compat: the column is nullable. Pre-existing Games
have ``library_id IS NULL`` and the importer falls back to a
platform-routed lookup (and ultimately the first library) so
the old single-library setup still works.

Revision ID: 0018_game_library_id
Revises: 0017_queue_entry_title_game
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_game_library_id"
down_revision = "0017_queue_entry_title_game"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("game") as batch:
        batch.add_column(sa.Column("library_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_game_library_id",
            "library",
            ["library_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("idx_game_library_id", ["library_id"])


def downgrade() -> None:
    with op.batch_alter_table("game") as batch:
        batch.drop_index("idx_game_library_id")
        batch.drop_constraint("fk_game_library_id", type_="foreignkey")
        batch.drop_column("library_id")
