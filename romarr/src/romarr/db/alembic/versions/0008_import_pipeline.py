"""Spec 008 — Import Pipeline schema.

One new table (``import_history``) plus three column additions on
the existing ``unidentified_dump`` table from foundation.

Forward-reference contract: the FK on
``unidentified_dump.library_id`` is gated on the ``library`` table
already existing. If spec 009 (Library) shipped first, the FK
lands here directly. If spec 008 shipped first, this migration
queues the column without an FK; spec 009's migration finalises
the FK on a subsequent ``alembic upgrade``.

The same gating pattern is documented in spec 009's
``0009_libraries`` migration, which detects the column and
finalises the FK iff present.

Revision ID: 0008_import_pipeline
Revises: 0009_libraries
Create Date: 2026-05-01
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

revision = "0008_import_pipeline"
down_revision = "0009_libraries"
branch_labels = None
depends_on = None


def _has_table(bind: Connection, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "import_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("dest_path", sa.String(), nullable=True),
        sa.Column(
            "download_client_id",
            sa.Integer(),
            sa.ForeignKey("download_client.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "download_client_native_id", sa.String(), nullable=True
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
            "dump_id",
            sa.Integer(),
            sa.ForeignKey("dump.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_hash_sha1", sa.String(40), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 2), nullable=True),
        sa.Column("imported_via", sa.String(16), nullable=False),
        sa.Column(
            "success", sa.Boolean(), nullable=False
        ),
        sa.Column(
            "coalesced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("warning", sa.String(), nullable=True),
        sa.Column("error_msg", sa.String(), nullable=True),
        sa.Column("imported_by", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "finished_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "imported_via IN "
            "('automatic','manual','rss','api','webhook')",
            name="ck_import_history_imported_via",
        ),
    )
    op.create_index(
        "idx_import_history_started_at", "import_history", ["started_at"]
    )
    op.create_index(
        "idx_import_history_release_started",
        "import_history",
        ["release_id", "started_at"],
    )
    op.create_index(
        "idx_import_history_correlation",
        "import_history",
        ["correlation_id"],
    )
    op.create_index(
        "idx_import_history_native_id",
        "import_history",
        ["download_client_native_id"],
    )
    op.create_index(
        "idx_import_history_success", "import_history", ["success"]
    )

    # unidentified_dump column extensions.
    library_exists = _has_table(bind, "library")
    with op.batch_alter_table("unidentified_dump") as batch_op:
        batch_op.add_column(
            sa.Column("rejection_reason", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("library_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("suggested_game_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_unidentified_dump_suggested_game",
            "game",
            ["suggested_game_id"],
            ["id"],
            ondelete="SET NULL",
        )
        if library_exists:
            batch_op.create_foreign_key(
                "fk_unidentified_dump_library",
                "library",
                ["library_id"],
                ["id"],
                ondelete="SET NULL",
            )
        batch_op.create_index(
            "idx_unidentified_dump_rejection",
            ["rejection_reason"],
        )


def downgrade() -> None:
    with op.batch_alter_table("unidentified_dump") as batch_op:
        batch_op.drop_index("idx_unidentified_dump_rejection")
        # Drop both FKs unconditionally; alembic ignores missing ones
        # in batch mode, but inspector-gate to be safe on Postgres.
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        existing = {
            fk.get("name") for fk in inspector.get_foreign_keys("unidentified_dump")
        }
        if "fk_unidentified_dump_library" in existing:
            batch_op.drop_constraint(
                "fk_unidentified_dump_library", type_="foreignkey"
            )
        if "fk_unidentified_dump_suggested_game" in existing:
            batch_op.drop_constraint(
                "fk_unidentified_dump_suggested_game", type_="foreignkey"
            )
        batch_op.drop_column("suggested_game_id")
        batch_op.drop_column("library_id")
        batch_op.drop_column("rejection_reason")

    op.drop_index("idx_import_history_success", table_name="import_history")
    op.drop_index("idx_import_history_native_id", table_name="import_history")
    op.drop_index(
        "idx_import_history_correlation", table_name="import_history"
    )
    op.drop_index(
        "idx_import_history_release_started", table_name="import_history"
    )
    op.drop_index(
        "idx_import_history_started_at", table_name="import_history"
    )
    op.drop_table("import_history")
