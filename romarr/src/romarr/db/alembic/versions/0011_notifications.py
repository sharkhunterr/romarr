"""Spec 011 — Notifications & Health schema.

Two new tables: ``notification`` (operator-configured Apprise
targets + per-event subscription flags + tag filters + optional
Jinja2 template overrides) and ``health_check`` (per-component
current state with persisted ``last_emitted_state`` for the
debouncer that survives process restarts — Q2 clarification).

No FKs into other features; both tables are standalone.

Revision ID: 0011_notifications
Revises: 0008_import_pipeline
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_notifications"
down_revision = "0008_import_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "apprise_url_encrypted", sa.LargeBinary(), nullable=False
        ),
        sa.Column("apprise_url_scheme", sa.String(32), nullable=False),
        sa.Column(
            "on_grab",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "on_import",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "on_upgrade",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "on_fail",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "on_health_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "on_dat_update",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "on_game_added",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "include_health_warnings",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "include_health_errors",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("on_grab_format", sa.String(), nullable=True),
        sa.Column("on_import_format", sa.String(), nullable=True),
        sa.Column("on_upgrade_format", sa.String(), nullable=True),
        sa.Column("on_fail_format", sa.String(), nullable=True),
        sa.Column("on_health_issue_format", sa.String(), nullable=True),
        sa.Column("on_dat_update_format", sa.String(), nullable=True),
        sa.Column("on_game_added_format", sa.String(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(16), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.UniqueConstraint("name", name="uq_notification_name"),
        sa.CheckConstraint(
            "last_status IS NULL OR "
            "last_status IN ('success','failed','partial')",
            name="ck_notification_last_status",
        ),
    )
    op.create_index("idx_notification_enabled", "notification", ["enabled"])

    op.create_table(
        "health_check",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("component", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column(
            "severity_changed_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "last_checked_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("last_emitted_state", sa.String(16), nullable=True),
        sa.Column(
            "last_emitted_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.UniqueConstraint("component", name="uq_health_check_component"),
        sa.CheckConstraint(
            "status IN ('ok','warning','error')",
            name="ck_health_check_status",
        ),
        sa.CheckConstraint(
            "last_emitted_state IS NULL OR "
            "last_emitted_state IN ('ok','warning','error')",
            name="ck_health_check_last_emitted_state",
        ),
    )
    op.create_index("idx_health_check_status", "health_check", ["status"])
    op.create_index(
        "idx_health_check_severity_changed_at",
        "health_check",
        ["severity_changed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_health_check_severity_changed_at", table_name="health_check"
    )
    op.drop_index("idx_health_check_status", table_name="health_check")
    op.drop_table("health_check")

    op.drop_index("idx_notification_enabled", table_name="notification")
    op.drop_table("notification")
