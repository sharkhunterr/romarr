"""Slice 466 — ``rom_pack.import_mode`` column.

Operator-tunable scope for a pack ingest:

- ``all`` (default) — every extracted ROM goes through the
  importer. DAT-verified hits create their Game from the DAT
  name; non-DAT files get a metadata-provider lookup
  (filename + platform) and import against the closest match.
  When the lookup finds nothing confident, the file falls to
  manual triage as ``unmatched``.
- ``dat_verified`` — only DAT-matched ROMs are imported.
  Non-DAT files are skipped entirely (no ``rom_pack_item`` row
  created) — the strictest setting.

Revision ID: 0032_rom_pack_import_mode
Revises: 0031_queue_entry_internal_downloads
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_rom_pack_import_mode"
down_revision = "0031_queue_entry_internal_downloads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rom_pack") as batch:
        batch.add_column(
            sa.Column(
                "import_mode",
                sa.String(length=16),
                nullable=False,
                server_default="all",
            )
        )
        batch.create_check_constraint(
            "ck_rom_pack_import_mode",
            "import_mode IN ('all', 'dat_verified')",
        )


def downgrade() -> None:
    with op.batch_alter_table("rom_pack") as batch:
        batch.drop_constraint("ck_rom_pack_import_mode", type_="check")
        batch.drop_column("import_mode")
