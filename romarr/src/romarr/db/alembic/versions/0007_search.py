"""Spec 007 — Search & Decision Engine schema.

Three new tables (``blocklist``, ``search_history``, ``search_cache``)
plus a single column addition on the existing ``indexer`` table
(``rss_auto_grab BOOLEAN NOT NULL DEFAULT true``).

Indexer FKs across the three audit tables are nullable + ON DELETE
SET NULL so deleting a configured indexer doesn't wipe the
historical record (FR-022). The cache CASCADE'es on indexer delete
because orphaned cache rows are noise — re-fetch is the right
recovery.

Revision ID: 0007_search
Revises: 0006_profiles
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_search"
down_revision = "0006_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blocklist",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "indexer_id",
            sa.Integer(),
            sa.ForeignKey("indexer.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("indexer_guid", sa.String(), nullable=True),
        sa.Column("release_title", sa.String(), nullable=False),
        sa.Column("hash_sha1", sa.String(40), nullable=True),
        sa.Column("hash_crc32", sa.String(8), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column(
            "added_by",
            sa.String(64),
            nullable=False,
            server_default="system",
        ),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_blocklist_indexer_guid", "blocklist", ["indexer_id", "indexer_guid"]
    )
    op.create_index("idx_blocklist_hash_sha1", "blocklist", ["hash_sha1"])
    op.create_index("idx_blocklist_hash_crc32", "blocklist", ["hash_crc32"])
    op.create_index("idx_blocklist_added_at", "blocklist", ["added_at"])

    op.create_table(
        "search_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_type", sa.String(32), nullable=False),
        sa.Column("query", sa.String(), nullable=True),
        sa.Column(
            "indexer_id",
            sa.Integer(),
            sa.ForeignKey("indexer.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("game.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "release_id",
            sa.Integer(),
            sa.ForeignKey("release.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "results_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "grabbed_release_id",
            sa.Integer(),
            sa.ForeignKey("release.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("chosen_indexer_guid", sa.String(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("no_grab_reason", sa.String(), nullable=True),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.CheckConstraint(
            "search_type IN ('manual','auto_added','missing_scheduled',"
            "'cutoff_scheduled','rss')",
            name="ck_search_history_search_type",
        ),
    )
    op.create_index(
        "idx_search_history_started_at", "search_history", ["started_at"]
    )
    op.create_index(
        "idx_search_history_game_started",
        "search_history",
        ["game_id", "started_at"],
    )
    op.create_index(
        "idx_search_history_type_started",
        "search_history",
        ["search_type", "started_at"],
    )
    op.create_index(
        "idx_search_history_correlation",
        "search_history",
        ["correlation_id"],
    )

    op.create_table(
        "search_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "indexer_id",
            sa.Integer(),
            sa.ForeignKey("indexer.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("category_ids", sa.JSON(), nullable=False),
        sa.Column("response_xml", sa.LargeBinary(), nullable=False),
        sa.Column("parsed_results", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_read_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "indexer_id", "cache_key", name="uq_search_cache_indexer_key"
        ),
    )
    op.create_index(
        "idx_search_cache_expires_at", "search_cache", ["expires_at"]
    )
    op.create_index(
        "idx_search_cache_last_read_at", "search_cache", ["last_read_at"]
    )

    # Single-column addition on indexer. SQLAlchemy/Alembic on SQLite
    # supports ALTER TABLE ADD COLUMN, but doesn't support
    # IF NOT EXISTS — so use batch_alter_table for portability.
    with op.batch_alter_table("indexer") as batch_op:
        batch_op.add_column(
            sa.Column(
                "rss_auto_grab",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("indexer") as batch_op:
        batch_op.drop_column("rss_auto_grab")

    op.drop_index("idx_search_cache_last_read_at", table_name="search_cache")
    op.drop_index("idx_search_cache_expires_at", table_name="search_cache")
    op.drop_table("search_cache")

    op.drop_index("idx_search_history_correlation", table_name="search_history")
    op.drop_index(
        "idx_search_history_type_started", table_name="search_history"
    )
    op.drop_index(
        "idx_search_history_game_started", table_name="search_history"
    )
    op.drop_index(
        "idx_search_history_started_at", table_name="search_history"
    )
    op.drop_table("search_history")

    op.drop_index("idx_blocklist_added_at", table_name="blocklist")
    op.drop_index("idx_blocklist_hash_crc32", table_name="blocklist")
    op.drop_index("idx_blocklist_hash_sha1", table_name="blocklist")
    op.drop_index("idx_blocklist_indexer_guid", table_name="blocklist")
    op.drop_table("blocklist")
