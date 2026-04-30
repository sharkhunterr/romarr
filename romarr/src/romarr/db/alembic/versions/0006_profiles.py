"""Spec 006 — Profiles schema.

Creates six profile tables (Quality, Region, Dump, Language,
Naming, Custom Format) plus the ``library_custom_format`` m2m. Each
profile table carries the FR-003a seeder sentinels (``seed_key`` +
``is_user_modified``) and ``is_factory_default`` for tagging
seeded rows.

The Library FK columns are owned by spec 009's migration once the
``library`` table lands; this migration creates the m2m table with
``library_id`` + ``custom_format_id`` + composite PK + the FK on
``custom_format_id`` ONLY. The deferred FK on ``library_id`` is
added by spec 009 (forward-reference pattern matching spec 005's
``indexer.download_client_id``).

Revision ID: 0006_profiles
Revises: 0005_download_clients
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0006_profiles"
down_revision = "0005_download_clients"
branch_labels = None
depends_on = None


def _profile_columns() -> list[Any]:
    """Shared columns across the six profile tables."""
    return [
        sa.Column("seed_key", sa.String(128), nullable=True),
        sa.Column(
            "is_user_modified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_factory_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "quality_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "allowed_formats",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("preferred_format", sa.String(32), nullable=False),
        sa.Column(
            "require_dat_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "allow_archive_double_compression",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("upgrade_until_format", sa.String(32), nullable=False),
        *_profile_columns(),
        sa.UniqueConstraint("name", name="uq_quality_profile_name"),
    )

    op.create_table(
        "region_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "priorities",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "allow_fallback_outside_priorities",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "exclude_regions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        *_profile_columns(),
        sa.UniqueConstraint("name", name="uq_region_profile_name"),
    )

    op.create_table(
        "dump_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "allowed_dump_status",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[\"verified\"]'"),
        ),
        sa.Column(
            "allow_proto_beta",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "allow_hacks",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "allow_trainers",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "allow_translations",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "prefer_revision",
            sa.String(8),
            nullable=False,
            server_default="latest",
        ),
        *_profile_columns(),
        sa.UniqueConstraint("name", name="uq_dump_profile_name"),
        sa.CheckConstraint(
            "prefer_revision IN ('latest','first','any')",
            name="ck_dump_profile_prefer_revision",
        ),
    )

    op.create_table(
        "language_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "required_languages",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "preferred_languages",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "exclude_japanese_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        *_profile_columns(),
        sa.UniqueConstraint("name", name="uq_language_profile_name"),
    )

    op.create_table(
        "naming_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("convention", sa.String(16), nullable=False),
        sa.Column("template", sa.String(), nullable=False),
        sa.Column(
            "platform_subfolder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "replace_illegal_chars",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "multi_disc_subfolder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        *_profile_columns(),
        sa.UniqueConstraint("name", name="uq_naming_profile_name"),
        sa.CheckConstraint(
            "convention IN ('no-intro','redump','tosec','es-de','romm','custom')",
            name="ck_naming_profile_convention",
        ),
    )

    op.create_table(
        "custom_format",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        *_profile_columns(),
        sa.UniqueConstraint("name", name="uq_custom_format_name"),
        sa.CheckConstraint(
            "score BETWEEN -10000 AND 10000",
            name="ck_custom_format_score",
        ),
    )

    # Partial unique index on seed_key — supported by both SQLite and
    # PostgreSQL. Lets a row carry NULL seed_key without conflicting,
    # while seeded rows must remain unique by seed_key (FR-003a).
    for table in (
        "quality_profile",
        "region_profile",
        "dump_profile",
        "language_profile",
        "naming_profile",
        "custom_format",
    ):
        op.create_index(
            f"idx_{table}_seed_key",
            table,
            ["seed_key"],
            unique=True,
            sqlite_where=sa.text("seed_key IS NOT NULL"),
            postgresql_where=sa.text("seed_key IS NOT NULL"),
        )

    # m2m: created with both columns + composite PK + FK on
    # custom_format_id. The FK on library_id is added by spec 009
    # once the library table exists.
    op.create_table(
        "library_custom_format",
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column(
            "custom_format_id",
            sa.Integer(),
            sa.ForeignKey("custom_format.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "library_id", "custom_format_id", name="pk_library_custom_format"
        ),
    )


def downgrade() -> None:
    op.drop_table("library_custom_format")
    for table in (
        "custom_format",
        "naming_profile",
        "language_profile",
        "dump_profile",
        "region_profile",
        "quality_profile",
    ):
        op.drop_index(f"idx_{table}_seed_key", table_name=table)
        op.drop_table(table)
