"""Spec 005 — Download Clients schema.

Creates the ``download_client`` table and finally installs the FK
constraint on ``indexer.download_client_id`` that was deferred from
migration 0004 (the column existed but was unconstrained because the
target table didn't yet exist).

ON DELETE SET NULL is intentional: deleting a pinned client falls
the affected indexer back to priority-based routing rather than
blocking the operation.

Revision ID: 0005_download_clients
Revises: 0004_indexers
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_download_clients"
down_revision = "0004_indexers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_client",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column(
            "use_ssl", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("url_base", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("password_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "category_default",
            sa.String(64),
            nullable=False,
            server_default="romarr",
        ),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column(
            "priority", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "enable_for_torrents",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "enable_for_usenet",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "remove_completed_downloads",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "remove_failed_downloads",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "ssl_cert_validation",
            sa.String(32),
            nullable=False,
            server_default="enabled",
        ),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_ok", sa.Boolean(), nullable=True),
        sa.Column("last_health_error", sa.String(), nullable=True),
        sa.Column("client_version_seen", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "type", "host", "port", name="uq_download_client_type_host_port"
        ),
        sa.CheckConstraint(
            "type IN ('qbittorrent','sabnzbd','transmission','deluge','nzbget')",
            name="ck_download_client_type",
        ),
        sa.CheckConstraint(
            "ssl_cert_validation IN ('enabled','disabled','disabled-for-local')",
            name="ck_download_client_ssl_validation",
        ),
        sa.CheckConstraint(
            "port BETWEEN 1 AND 65535",
            name="ck_download_client_port_range",
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 100",
            name="ck_download_client_priority_range",
        ),
    )
    op.create_index(
        "idx_download_client_enabled", "download_client", ["enabled"]
    )

    # Deferred FK from spec 004's indexer.download_client_id column.
    # SQLite supports this through table reconstruction; PostgreSQL
    # via ALTER TABLE — Alembic's batch mode picks the right path.
    with op.batch_alter_table("indexer") as batch_op:
        batch_op.create_foreign_key(
            "fk_indexer_download_client_id",
            "download_client",
            ["download_client_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("indexer") as batch_op:
        batch_op.drop_constraint(
            "fk_indexer_download_client_id", type_="foreignkey"
        )
    op.drop_index(
        "idx_download_client_enabled", table_name="download_client"
    )
    op.drop_table("download_client")
