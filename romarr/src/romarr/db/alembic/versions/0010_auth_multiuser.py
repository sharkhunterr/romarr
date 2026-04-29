"""Spec 010 — Auth & Multi-User schema.

Creates four tables:
  - ``user`` — single ``role`` column (no ``is_superuser``)
  - ``session`` — sliding 30-day TTL columns
  - ``api_key`` — coarse 3-tier scopes JSON, BLAKE2b key_hash
  - ``setup_token`` — one-shot bootstrap

Also seeds the ``system`` sentinel user (id=0) so existing ``*_by``
text columns (introduced by earlier specs) can be backfilled to
INTEGER FKs once those specs are implemented. The ``*_by`` column
type changes themselves are NOT in this migration — each owning
spec performs the backfill in its own migration to keep the
ordering safe.

Revision ID: 0010_auth_multiuser
Revises: 0001_initial_schema
Create Date: 2026-04-29
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "0010_auth_multiuser"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("oidc_subject", sa.String(255), nullable=True),
        sa.Column("oidc_provider", sa.String(64), nullable=True),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username", name="uq_user_username"),
        sa.UniqueConstraint("email", name="uq_user_email"),
        sa.UniqueConstraint(
            "oidc_provider", "oidc_subject", name="uq_user_oidc_identity"
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'user', 'readonly')",
            name="ck_user_role",
        ),
    )
    op.create_index("ix_user_username", "user", ["username"])

    op.create_table(
        "session",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_session_user_id", "session", ["user_id"])
    op.create_index("ix_session_expires_at", "session", ["expires_at"])

    op.create_table(
        "api_key",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default='["read"]'),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key_hash", name="uq_api_key_hash"),
    )
    op.create_index("ix_api_key_user_id", "api_key", ["user_id"])
    op.create_index("ix_api_key_hash", "api_key", ["key_hash"])

    op.create_table(
        "setup_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_setup_token_hash"),
    )

    # Seed the ``system`` sentinel user (id=0). Pre-existing rows from
    # earlier specs that carry imported_by='system' / applied_by='system'
    # / added_by='system' will reference this row when each owning
    # spec migrates its ``*_by`` column from VARCHAR to INTEGER FK.
    now = datetime(2026, 4, 29, 0, 0, 0, tzinfo=UTC)
    user_table = sa.table(
        "user",
        sa.column("id"),
        sa.column("username"),
        sa.column("email"),
        sa.column("hashed_password"),
        sa.column("is_active"),
        sa.column("role"),
        sa.column("preferences", sa.JSON()),
        sa.column("created_at"),
        sa.column("updated_at"),
    )
    op.bulk_insert(
        user_table,
        [
            {
                "id": 0,
                "username": "system",
                "email": None,
                "hashed_password": None,
                "is_active": False,  # sentinel only — cannot log in
                "role": "admin",
                "preferences": {},
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("setup_token")
    op.drop_table("api_key")
    op.drop_table("session")
    op.drop_index("ix_user_username", table_name="user")
    op.drop_table("user")
