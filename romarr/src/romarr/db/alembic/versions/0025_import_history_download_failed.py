"""Slice 438 — widen ``import_history.imported_via`` CHECK.

Adds the literal ``'download_failed'`` so the queue_reconciler
can write a synthetic ``ImportHistory`` row when a download
transitions to FAILED (HTML payload, checksum mismatch, upstream
4xx mid-stream, etc.). Pre-slice the failure stayed inside
``queue_entry`` only — the History tab on Activity (which pulls
from ``import_history`` ∪ ``search_history`` ∪ ``job_run``)
showed nothing, and operators had to grep the container logs
to figure out why a queued grab never completed.

Revision ID: 0025_import_history_download_failed
Revises: 0024_indexer_enabled_master_switch
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op


revision = "0025_import_history_download_failed"
down_revision = "0024_indexer_enabled_master_switch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_history") as batch_op:
        batch_op.drop_constraint(
            "ck_import_history_imported_via", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_import_history_imported_via",
            "imported_via IN "
            "('automatic','manual','rss','api','webhook','scan','download_failed')",
        )


def downgrade() -> None:
    # Clamp any rows on the new literal before re-tightening so
    # the recreate doesn't fail on existing data.
    op.execute(
        "DELETE FROM import_history WHERE imported_via = 'download_failed'"
    )
    with op.batch_alter_table("import_history") as batch_op:
        batch_op.drop_constraint(
            "ck_import_history_imported_via", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_import_history_imported_via",
            "imported_via IN "
            "('automatic','manual','rss','api','webhook','scan')",
        )
