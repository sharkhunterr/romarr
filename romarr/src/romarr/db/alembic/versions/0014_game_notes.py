"""Spec 014 slice 149 — operator-owned notes column on Game.

Adds:

  * ``game.notes`` — free-text column the operator can fill via
    the GameDetail Notes tab. Distinct from any aggregator-owned
    field; never overwritten by the spec-002 metadata refresh
    cascade. Nullable; ``NULL`` is the empty state.

The notes string is bounded only by the SQLite/Postgres TEXT
limit, which in practice is "more than any operator will type".

Revision ID: 0014_game_notes
Revises: 0013_rest_api
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_game_notes"
down_revision = "0013_rest_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("game") as batch:
        batch.add_column(sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("game") as batch:
        batch.drop_column("notes")
