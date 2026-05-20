"""Slice 478 — extend ``queue_entry.state`` CHECK.

The ROM-pack ingest pipeline mirrors itself into ``queue_entry``
so the operator watches the whole download → extract → import
flow inside Activity → Queue. Slice 475 added ``state =
'extracting'`` / ``'importing'`` writes; the existing CHECK
constraint rejected them and the runner crashed mid-ingest with
``IntegrityError: ck_queue_entry_state``.

Drop the old CHECK and re-create it with the two new values
admitted. SQLite needs ``batch_alter_table`` to rebuild the
table for a constraint swap.

Revision ID: 0034_queue_entry_state_extracting_importing
Revises: 0033_rom_pack_unknown_action
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op

revision = "0034_queue_entry_state_extracting_importing"
down_revision = "0033_rom_pack_unknown_action"
branch_labels = None
depends_on = None


_NEW_CHECK = (
    "state IN ("
    "'queued', 'downloading', 'paused', 'completed', "
    "'stuck', 'failed', 'pending_retry', "
    "'extracting', 'importing'"
    ")"
)
_OLD_CHECK = (
    "state IN ("
    "'queued', 'downloading', 'paused', 'completed', "
    "'stuck', 'failed', 'pending_retry'"
    ")"
)


def upgrade() -> None:
    with op.batch_alter_table("queue_entry") as batch:
        batch.drop_constraint("ck_queue_entry_state", type_="check")
        batch.create_check_constraint(
            "ck_queue_entry_state", _NEW_CHECK
        )


def downgrade() -> None:
    # Refuse the downgrade if any row still carries one of the new
    # values — there's nothing safe to coerce them to.
    import sqlalchemy as sa

    bind = op.get_bind()
    invalid = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM queue_entry "
            "WHERE state IN ('extracting', 'importing')"
        )
    ).scalar()
    if invalid and invalid > 0:
        raise RuntimeError(
            f"queue_entry has {invalid} rows in 'extracting'/'importing'; "
            "let them settle before downgrading."
        )
    with op.batch_alter_table("queue_entry") as batch:
        batch.drop_constraint("ck_queue_entry_state", type_="check")
        batch.create_check_constraint(
            "ck_queue_entry_state", _OLD_CHECK
        )
