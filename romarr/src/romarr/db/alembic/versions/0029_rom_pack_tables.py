"""Slice 460 — ``rom_pack`` + ``rom_pack_item`` tables.

ROM content packs: a downloadable archive holding many ROMs (a
No-Intro full set, an archive.org romset, a curated bundle).
The ingest task downloads + extracts the archive and runs every
ROM through the importer; one ``rom_pack_item`` row tracks each
file's outcome (imported / unmatched / parked / deleted /
failed).

Distinct from ``platform_pack`` — that's *platform metadata*,
this is actual ROM content.

Revision ID: 0029_rom_pack_tables
Revises: 0028_platform_slug_gameboy_to_gb
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_rom_pack_tables"
down_revision = "0028_platform_slug_gameboy_to_gb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rom_pack",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "source_kind",
            sa.String(length=8),
            nullable=False,
            server_default="url",
        ),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("download_client_id", sa.Integer(), nullable=True),
        sa.Column(
            "download_client_native_id", sa.String(length=255), nullable=True
        ),
        sa.Column(
            "platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("max_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("downloaded_path", sa.String(length=2048), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "total_files", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "imported_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "unmatched_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "parked_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "failed_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "last_ingest_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "source_kind IN ('url', 'grab')",
            name="ck_rom_pack_source_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending','downloading','extracting','importing',"
            "'awaiting_triage','done','failed')",
            name="ck_rom_pack_status",
        ),
        sa.CheckConstraint(
            "(source_kind = 'url' AND url IS NOT NULL) "
            "OR (source_kind = 'grab' "
            "AND download_client_native_id IS NOT NULL)",
            name="ck_rom_pack_source_fields",
        ),
    )
    op.create_index(
        "ix_rom_pack_platform_id", "rom_pack", ["platform_id"]
    )
    op.create_index("ix_rom_pack_status", "rom_pack", ["status"])

    op.create_table(
        "rom_pack_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "rom_pack_id",
            sa.Integer(),
            sa.ForeignKey("rom_pack.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("extracted_path", sa.String(length=2048), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("crc32", sa.String(length=8), nullable=True),
        sa.Column("md5", sa.String(length=32), nullable=True),
        sa.Column("sha1", sa.String(length=40), nullable=True),
        sa.Column(
            "status",
            sa.String(length=12),
            nullable=False,
            server_default="unmatched",
        ),
        sa.Column(
            "dat_entry_id",
            sa.Integer(),
            sa.ForeignKey("dat_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("game.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "dump_id",
            sa.Integer(),
            sa.ForeignKey("dump.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_msg", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('imported','unmatched','parked','deleted','failed')",
            name="ck_rom_pack_item_status",
        ),
    )
    op.create_index(
        "ix_rom_pack_item_rom_pack_id", "rom_pack_item", ["rom_pack_id"]
    )
    op.create_index(
        "ix_rom_pack_item_status", "rom_pack_item", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_rom_pack_item_status", table_name="rom_pack_item")
    op.drop_index(
        "ix_rom_pack_item_rom_pack_id", table_name="rom_pack_item"
    )
    op.drop_table("rom_pack_item")
    op.drop_index("ix_rom_pack_status", table_name="rom_pack")
    op.drop_index("ix_rom_pack_platform_id", table_name="rom_pack")
    op.drop_table("rom_pack")
