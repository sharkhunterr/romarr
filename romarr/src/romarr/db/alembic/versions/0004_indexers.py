"""Spec 004 — Indexers schema.

Creates two new tables: ``indexer`` and ``application``.

The ``indexer.download_client_id`` column is added without a FK
because the ``download_client`` table arrives in spec 005 — that
migration adds the FK once the target table exists.

Revision ID: 0004_indexers
Revises: 0003_platform_packs
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_indexers"
down_revision = "0003_platform_packs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "sync_level",
            sa.String(16),
            nullable=False,
            server_default="full_sync",
        ),
        sa.Column("prowlarr_url", sa.String(), nullable=False),
        sa.Column(
            "prowlarr_api_key_encrypted", sa.LargeBinary(), nullable=False
        ),
        sa.Column("app_token_hash", sa.String(255), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "prowlarr_url", name="uq_application_prowlarr_url"
        ),
        sa.CheckConstraint(
            "sync_level IN ('disabled','add_only','full_sync')",
            name="ck_application_sync_level",
        ),
    )

    op.create_table(
        "indexer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("implementation", sa.String(16), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "categories",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "priority", sa.Integer(), nullable=False, server_default="25"
        ),
        sa.Column(
            "enable_rss",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "enable_automatic_search",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "enable_interactive_search",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column(
            "rate_limit_seconds",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "min_seeders", sa.Integer(), nullable=False, server_default="1"
        ),
        # FK to download_client.id added in spec 005's migration.
        sa.Column("download_client_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "prowlarr_app_id",
            sa.Integer(),
            sa.ForeignKey("application.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("seed_ratio", sa.Numeric(4, 2), nullable=True),
        sa.Column("seed_time_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "discount_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "priority_indexer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column(
            "result_limit",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_ok", sa.Boolean(), nullable=True),
        sa.Column("last_health_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "implementation", "url", name="uq_indexer_impl_url"
        ),
        sa.CheckConstraint(
            "implementation IN ('newznab','torznab')",
            name="ck_indexer_implementation",
        ),
        sa.CheckConstraint(
            "source IN ('manual','prowlarr')", name="ck_indexer_source"
        ),
        sa.CheckConstraint(
            "rate_limit_seconds >= 0", name="ck_indexer_rate_limit_nonneg"
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 100", name="ck_indexer_priority_range"
        ),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 5 AND 120",
            name="ck_indexer_timeout_range",
        ),
        sa.CheckConstraint(
            "result_limit BETWEEN 1 AND 500",
            name="ck_indexer_result_limit_range",
        ),
    )
    op.create_index("idx_indexer_source", "indexer", ["source"])


def downgrade() -> None:
    op.drop_index("idx_indexer_source", table_name="indexer")
    op.drop_table("indexer")
    op.drop_table("application")
