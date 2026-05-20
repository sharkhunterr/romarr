"""Slice 472 — ``rom_pack.unknown_action`` column.

Operator-chosen fallback for non-DAT, non-metadata-matched ROMs
in ``import_mode='all'``. Before this slice every unresolved
ROM landed as ``unmatched`` and required manual triage. The
operator can now pick the policy at pack-creation time:

- ``triage`` (default) — the legacy behaviour: the ROM keeps
  its extracted file, status flips to ``unmatched`` and shows
  up in the pack detail modal for per-file resolution.
- ``park`` — auto-park into ``unidentified_dump`` so the ROM
  surfaces under Settings → Unidentified for later work.
- ``delete`` — drop the extracted file outright, no row kept.
  The strictest "exclude" choice.

``import_mode='dat_verified'`` ignores this field — those
packs skip non-DAT files unconditionally.

Revision ID: 0033_rom_pack_unknown_action
Revises: 0032_rom_pack_import_mode
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_rom_pack_unknown_action"
down_revision = "0032_rom_pack_import_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rom_pack") as batch:
        batch.add_column(
            sa.Column(
                "unknown_action",
                sa.String(length=12),
                nullable=False,
                server_default="triage",
            )
        )
        batch.create_check_constraint(
            "ck_rom_pack_unknown_action",
            "unknown_action IN ('triage', 'park', 'delete')",
        )


def downgrade() -> None:
    with op.batch_alter_table("rom_pack") as batch:
        batch.drop_constraint("ck_rom_pack_unknown_action", type_="check")
        batch.drop_column("unknown_action")
