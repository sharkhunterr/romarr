"""Add ``import_history.size_bytes`` for timeline display.

Per-game timeline redesign (slice 467) needs the imported file's
byte count to render a "5.4 GB" column alongside the existing
client + filename + duration fields. Other audit columns
(``source_path``, ``sha1``, ``dest_path``, ``duration_ms``) were
already enough for forensics; this one is purely operator-facing.

NULLable + no backfill: ``size_bytes`` is unknown for historical
rows and the UI renders ``—`` when absent. The orchestrator's
existing ``size_bytes`` local var (computed at hash time, line
~277) gets propagated through ``persist_*_history`` going
forward, so every NEW row carries the value.

Revision ID: 0036_import_history_size_bytes
Revises: 0035_quality_profile_auto_grab_min_score
Create Date: 2026-05-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036_import_history_size_bytes"
down_revision: Union[str, Sequence[str], None] = (
    "0035_quality_profile_auto_grab_min_score"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("import_history") as batch:
        batch.add_column(
            sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("import_history") as batch:
        batch.drop_column("size_bytes")
