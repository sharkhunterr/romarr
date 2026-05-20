"""Slice 464 — ``rom_pack_config`` singleton table.

Global defaults for the ROM-pack subsystem: where url-sourced
archives stream to disk, and the size ceiling a pack inherits
when it doesn't pin its own ``max_size_bytes``.

Exactly one row exists (``id = 1``); the API get-or-creates it.
The CHECK on ``id`` enforces the singleton at the DB level.

Revision ID: 0030_rom_pack_config
Revises: 0029_rom_pack_tables
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_rom_pack_config"
down_revision = "0029_rom_pack_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rom_pack_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "download_dir",
            sa.String(length=2048),
            nullable=False,
            server_default="/downloads/rom_packs",
        ),
        sa.Column(
            "default_max_size_bytes", sa.BigInteger(), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_rom_pack_config_singleton"),
    )


def downgrade() -> None:
    op.drop_table("rom_pack_config")
