"""Initial foundation schema + 5 MVP platforms seed.

Spec 001 FR-001: nine tables.
Spec 001 FR-009: seed 5 MVP platforms (NES, SNES, Mega Drive, Game Boy,
Game Boy Advance) with their primary formats marked
``pack_source = 'builtin'``.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-29
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def upgrade() -> None:
    op.create_table(
        "platform",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("short_name", sa.String(32), nullable=True),
        sa.Column("manufacturer", sa.String(64), nullable=True),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column(
            "parent_platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("igdb_id", sa.Integer(), nullable=True),
        sa.Column("screenscraper_id", sa.Integer(), nullable=True),
        sa.Column("mobygames_id", sa.Integer(), nullable=True),
        sa.Column("launchbox_id", sa.Integer(), nullable=True),
        sa.Column("retroachievements_id", sa.Integer(), nullable=True),
        sa.Column("newznab_category_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("pack_source", sa.String(16), nullable=False, server_default="builtin"),
        sa.Column("pack_version", sa.String(16), nullable=True),
        sa.Column("extra_meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_platform_slug"),
        sa.CheckConstraint(
            "pack_source IN ('builtin', 'community', 'user')",
            name="ck_platform_pack_source",
        ),
    )
    op.create_index("ix_platform_slug", "platform", ["slug"])

    op.create_table(
        "platform_format",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extension", sa.String(16), nullable=False),
        sa.Column("format_type", sa.String(16), nullable=False),
        sa.Column("min_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("max_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("pack_source", sa.String(16), nullable=False, server_default="builtin"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform_id", "extension", name="uq_platform_format"),
        sa.CheckConstraint(
            "format_type IN ('cartridge', 'disc', 'compressed', 'archive', 'package')",
            name="ck_platform_format_type",
        ),
        sa.CheckConstraint(
            "pack_source IN ('builtin', 'community', 'user')",
            name="ck_platform_format_pack_source",
        ),
    )

    op.create_table(
        "platform_naming_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("pattern", sa.String(512), nullable=False),
        sa.Column("meaning", sa.String(64), nullable=False),
        sa.Column(
            "convention", sa.String(16), nullable=False, server_default="no-intro"
        ),
        sa.Column("pack_source", sa.String(16), nullable=False, server_default="builtin"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform_id", "name", name="uq_platform_naming_token"),
        sa.CheckConstraint(
            "pack_source IN ('builtin', 'community', 'user')",
            name="ck_platform_naming_token_pack_source",
        ),
    )

    op.create_table(
        "game",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(192), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("sort_title", sa.String(255), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("cover_path", sa.String(), nullable=True),
        sa.Column("igdb_id", sa.Integer(), nullable=True),
        sa.Column("mobygames_id", sa.Integer(), nullable=True),
        sa.Column("screenscraper_id", sa.Integer(), nullable=True),
        sa.Column("launchbox_id", sa.Integer(), nullable=True),
        sa.Column("retroachievements_id", sa.Integer(), nullable=True),
        sa.Column("release_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("developer", sa.String(128), nullable=True),
        sa.Column("publisher", sa.String(128), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("age_rating", sa.String(16), nullable=True),
        sa.Column("players_min", sa.Integer(), nullable=True),
        sa.Column("players_max", sa.Integer(), nullable=True),
        sa.Column("hltb_main", sa.Integer(), nullable=True),
        sa.Column("achievements_count", sa.Integer(), nullable=True),
        sa.Column("genres", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("themes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("franchises", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("locked_fields", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("custom_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("monitored", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "needs_metadata_refresh",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform_id", "slug", name="uq_game_platform_slug"),
    )
    op.create_index("ix_game_platform_id", "game", ["platform_id"])
    op.create_index("idx_game_title", "game", ["title"])

    op.create_table(
        "release",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("game.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=True),
        sa.Column("regions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("languages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("revision", sa.String(32), nullable=True),
        sa.Column("dump_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column(
            "naming_convention", sa.String(16), nullable=False, server_default="unknown"
        ),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("disc_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("disc_total", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "parent_release_id",
            sa.Integer(),
            sa.ForeignKey("release.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="wanted"),
        sa.Column("monitored", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("cutoff_met", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(disc_number = 1) OR (parent_release_id IS NOT NULL)",
            name="ck_release_multidisc_parent",
        ),
        sa.CheckConstraint(
            "status IN ('wanted', 'imported', 'cutoff_met')",
            name="ck_release_status",
        ),
        sa.CheckConstraint("disc_number >= 1", name="ck_release_disc_number_positive"),
        sa.CheckConstraint("disc_total >= 1", name="ck_release_disc_total_positive"),
    )
    op.create_index("ix_release_game_id", "release", ["game_id"])
    op.create_index("ix_release_parent_release_id", "release", ["parent_release_id"])

    op.create_table(
        "dat_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("crc32", sa.String(8), nullable=True),
        sa.Column("md5", sa.String(32), nullable=True),
        sa.Column("sha1", sa.String(40), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="verified"),
        sa.Column("dat_contents_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(crc32 IS NOT NULL) OR (md5 IS NOT NULL) OR (sha1 IS NOT NULL)",
            name="ck_dat_entry_at_least_one_hash",
        ),
        sa.CheckConstraint(
            "source IN ('no-intro', 'redump', 'tosec', 'goodtools', "
            "'hasheous', 'playmatch', 'custom')",
            name="ck_dat_entry_source",
        ),
        sa.UniqueConstraint(
            "platform_id", "source", "sha1", name="uq_dat_entry_platform_source_sha1"
        ),
    )
    op.create_index("ix_dat_entry_platform_id", "dat_entry", ["platform_id"])
    op.create_index("ix_dat_entry_source", "dat_entry", ["source"])
    op.create_index("ix_dat_entry_sha1", "dat_entry", ["sha1"])
    op.create_index("ix_dat_entry_crc32", "dat_entry", ["crc32"])
    op.create_index("ix_dat_entry_md5", "dat_entry", ["md5"])

    op.create_table(
        "dump",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "release_id",
            sa.Integer(),
            sa.ForeignKey("release.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("crc32", sa.String(8), nullable=False),
        sa.Column("md5", sa.String(32), nullable=False),
        sa.Column("sha1", sa.String(40), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("dat_verified", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("dat_source", sa.String(16), nullable=True),
        sa.Column(
            "dat_entry_id",
            sa.Integer(),
            sa.ForeignKey("dat_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_by", sa.String(32), nullable=False, server_default="system"),
        sa.Column("imported_via", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("path", name="uq_dump_path"),
    )
    op.create_index("ix_dump_release_id", "dump", ["release_id"])
    op.create_index("ix_dump_path", "dump", ["path"])
    op.create_index("idx_dump_sha1", "dump", ["sha1"])
    op.create_index("idx_dump_crc32", "dump", ["crc32"])
    op.create_index("idx_dump_md5", "dump", ["md5"])

    op.create_table(
        "unidentified_dump",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("crc32", sa.String(8), nullable=True),
        sa.Column("md5", sa.String(32), nullable=True),
        sa.Column("sha1", sa.String(40), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "suggested_platform_id",
            sa.Integer(),
            sa.ForeignKey("platform.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("path", name="uq_unidentified_dump_path"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_unidentified_dump_attempts"),
    )

    op.create_table(
        "platform_pack",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pack_version", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("author", sa.String(128), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("contents_hash", sa.String(64), nullable=False),
        sa.Column("pack_source", sa.String(16), nullable=False, server_default="builtin"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_by", sa.String(32), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pack_version", name="uq_platform_pack_version"),
        sa.CheckConstraint(
            "pack_source IN ('builtin', 'community', 'user')",
            name="ck_platform_pack_source_pack",
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_platform_pack_schema_version"),
    )

    # -----------------------------------------------------------------------
    # Seed data — FR-009
    # -----------------------------------------------------------------------

    now = datetime(2026, 4, 29, 0, 0, 0, tzinfo=UTC)

    # Reflect the ad-hoc tables Alembic created so we can issue inserts.
    # JSON columns get the explicit `sa.JSON()` type so the dialect
    # adapter serialises lists/dicts to text instead of trying to bind
    # native Python collections.
    platform = sa.table(
        "platform",
        sa.column("id"),
        sa.column("slug"),
        sa.column("name"),
        sa.column("short_name"),
        sa.column("manufacturer"),
        sa.column("release_year"),
        sa.column("igdb_id"),
        sa.column("screenscraper_id"),
        sa.column("newznab_category_ids", sa.JSON()),
        sa.column("pack_source"),
        sa.column("pack_version"),
        sa.column("extra_meta", sa.JSON()),
        sa.column("created_at"),
        sa.column("updated_at"),
    )
    platform_format = sa.table(
        "platform_format",
        sa.column("platform_id"),
        sa.column("extension"),
        sa.column("format_type"),
        sa.column("pack_source"),
        sa.column("created_at"),
        sa.column("updated_at"),
    )
    platform_pack = sa.table(
        "platform_pack",
        sa.column("pack_version"),
        sa.column("schema_version"),
        sa.column("description"),
        sa.column("author"),
        sa.column("contents_hash"),
        sa.column("pack_source"),
        sa.column("applied_at"),
        sa.column("applied_by"),
        sa.column("created_at"),
        sa.column("updated_at"),
    )

    op.bulk_insert(
        platform_pack,
        [
            {
                "pack_version": "2026.04.001",
                "schema_version": 1,
                "description": "Romarr built-in platform pack — MVP 5 platforms",
                "author": "Romarr",
                "contents_hash": "0" * 64,
                "pack_source": "builtin",
                "applied_at": now,
                "applied_by": "system",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )

    op.bulk_insert(
        platform,
        [
            {
                "id": 1,
                "slug": "nes",
                "name": "Nintendo Entertainment System",
                "short_name": "NES",
                "manufacturer": "Nintendo",
                "release_year": 1983,
                "igdb_id": 18,
                "screenscraper_id": 3,
                "newznab_category_ids": [1060, 7010],
                "pack_source": "builtin",
                "pack_version": "2026.04.001",
                "extra_meta": {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": 2,
                "slug": "snes",
                "name": "Super Nintendo Entertainment System",
                "short_name": "SNES",
                "manufacturer": "Nintendo",
                "release_year": 1990,
                "igdb_id": 19,
                "screenscraper_id": 4,
                "newznab_category_ids": [1060, 7010],
                "pack_source": "builtin",
                "pack_version": "2026.04.001",
                "extra_meta": {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": 3,
                "slug": "megadrive",
                "name": "Sega Mega Drive",
                "short_name": "Mega Drive",
                "manufacturer": "Sega",
                "release_year": 1988,
                "igdb_id": 29,
                "screenscraper_id": 1,
                "newznab_category_ids": [1060, 7010],
                "pack_source": "builtin",
                "pack_version": "2026.04.001",
                "extra_meta": {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": 4,
                "slug": "gameboy",
                "name": "Nintendo Game Boy",
                "short_name": "Game Boy",
                "manufacturer": "Nintendo",
                "release_year": 1989,
                "igdb_id": 33,
                "screenscraper_id": 9,
                "newznab_category_ids": [1060, 7010],
                "pack_source": "builtin",
                "pack_version": "2026.04.001",
                "extra_meta": {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": 5,
                "slug": "gba",
                "name": "Nintendo Game Boy Advance",
                "short_name": "GBA",
                "manufacturer": "Nintendo",
                "release_year": 2001,
                "igdb_id": 24,
                "screenscraper_id": 12,
                "newznab_category_ids": [1060, 7010],
                "pack_source": "builtin",
                "pack_version": "2026.04.001",
                "extra_meta": {},
                "created_at": now,
                "updated_at": now,
            },
        ],
    )

    op.bulk_insert(
        platform_format,
        [
            # NES
            {
                "platform_id": 1,
                "extension": ".nes",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
            {
                "platform_id": 1,
                "extension": ".unf",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
            # SNES
            {
                "platform_id": 2,
                "extension": ".sfc",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
            {
                "platform_id": 2,
                "extension": ".smc",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
            # Mega Drive
            {
                "platform_id": 3,
                "extension": ".md",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
            {
                "platform_id": 3,
                "extension": ".bin",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
            {
                "platform_id": 3,
                "extension": ".gen",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
            # Game Boy
            {
                "platform_id": 4,
                "extension": ".gb",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
            # GBA
            {
                "platform_id": 5,
                "extension": ".gba",
                "format_type": "cartridge",
                "pack_source": "builtin",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("platform_pack")
    op.drop_table("unidentified_dump")
    op.drop_table("dump")
    op.drop_table("dat_entry")
    op.drop_table("release")
    op.drop_table("game")
    op.drop_table("platform_naming_token")
    op.drop_table("platform_format")
    op.drop_index("ix_platform_slug", table_name="platform")
    op.drop_table("platform")
