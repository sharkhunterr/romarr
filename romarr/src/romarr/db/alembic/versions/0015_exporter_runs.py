"""Spec 009 slice 326 — per-(library, exporter) last-run tracking.

Adds:

  * ``library_exporter_run`` table — one row per (library_id,
    exporter_name) tuple. Columns:

      - library_id     (FK → library.id, ON DELETE CASCADE)
      - exporter_name  (TEXT)
      - last_run_at    (DATETIME, nullable)
      - run_count      (INTEGER, default 0)
      - last_status    (TEXT — 'ok' | 'coalesced' | 'error', default 'ok')
      - last_error     (TEXT, nullable)

The orchestrator's per-import dispatch + the manual-run endpoint
both upsert this row on every successful emission so the
operator UI can surface "last successful gamelist.xml emit" per
library + exporter (FR-019 / T077).

Revision ID: 0015_exporter_runs
Revises: 0014_game_notes
Create Date: 2026-05-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_exporter_runs"
down_revision = "0014_game_notes"
branch_labels = None
depends_on = None


_STATUS_CHECK = "last_status IN ('ok','coalesced','error')"


def upgrade() -> None:
    op.create_table(
        "library_exporter_run",
        sa.Column(
            "library_id",
            sa.Integer(),
            sa.ForeignKey("library.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "exporter_name", sa.String(64), primary_key=True, nullable=False
        ),
        sa.Column(
            "last_run_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "run_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "last_status",
            sa.String(16),
            nullable=False,
            server_default="ok",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(_STATUS_CHECK, name="ck_library_exporter_run_status"),
    )


def downgrade() -> None:
    op.drop_table("library_exporter_run")
