"""Spec 013 — REST API & WebSocket schema additions.

Three new tables, all cross-cutting infrastructure that didn't fit
into any earlier spec:

  * ``tag`` — operator-defined tags (slug + colour + label).
  * ``tag_assignment`` — polymorphic m2m linking ``tag`` rows to
    Game / Indexer / Notification / Release rows. No FK on
    ``entity_id`` because the target table varies; per-entity
    cleanup is performed by application-layer hooks.
  * ``queue_entry`` — Romarr's mirror of the download client
    queue. Reconciler upserts on
    ``(download_client_id, download_client_native_id)``.
  * ``idempotency_cache`` — DB fallback for the FR-020 / FR-025
    Idempotency-Key cache. Composite PK ``(endpoint, key)``.

Brand-default ``tag.color`` is ``#9BBC0F`` (the Game Boy LCD green
clarified in spec 014).

Revision ID: 0013_rest_api
Revises: 0012_tasks
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_rest_api"
down_revision = "0012_tasks"
branch_labels = None
depends_on = None


_TAG_ENTITY_TYPE_CHECK = (
    "entity_type IN ('game', 'indexer', 'notification', 'release')"
)
_QUEUE_STATE_CHECK = (
    "state IN ("
    "'queued', 'downloading', 'paused', 'completed', "
    "'stuck', 'failed', 'pending_retry'"
    ")"
)


def upgrade() -> None:
    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column(
            "color",
            sa.String(),
            nullable=False,
            server_default=sa.text("'#9BBC0F'"),
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_tag_name", "tag", ["name"])

    op.create_table(
        "tag_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("tag.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "tag_id",
            "entity_type",
            "entity_id",
            name="uq_tag_assignment_unique",
        ),
        sa.CheckConstraint(
            _TAG_ENTITY_TYPE_CHECK, name="ck_tag_assignment_entity_type"
        ),
    )
    op.create_index(
        "idx_tag_assignment_lookup",
        "tag_assignment",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "idx_tag_assignment_tag", "tag_assignment", ["tag_id"]
    )

    op.create_table(
        "queue_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "release_id",
            sa.Integer(),
            sa.ForeignKey("release.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "download_client_id",
            sa.Integer(),
            sa.ForeignKey("download_client.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "download_client_native_id", sa.String(), nullable=False
        ),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column(
            "progress",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("eta_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("error_msg", sa.String(), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "last_attempt_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "download_client_id",
            "download_client_native_id",
            name="uq_queue_entry_native_id",
        ),
        sa.CheckConstraint(_QUEUE_STATE_CHECK, name="ck_queue_entry_state"),
    )
    op.create_index(
        "idx_queue_entry_release", "queue_entry", ["release_id"]
    )
    op.create_index("idx_queue_entry_state", "queue_entry", ["state"])

    op.create_table(
        "idempotency_cache",
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("request_body_hash", sa.String(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.LargeBinary(), nullable=False),
        sa.Column(
            "response_headers",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "endpoint", "key", name="pk_idempotency_cache"
        ),
    )
    op.create_index(
        "idx_idempotency_cache_expires_at",
        "idempotency_cache",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_idempotency_cache_expires_at",
        table_name="idempotency_cache",
    )
    op.drop_table("idempotency_cache")

    op.drop_index("idx_queue_entry_state", table_name="queue_entry")
    op.drop_index("idx_queue_entry_release", table_name="queue_entry")
    op.drop_table("queue_entry")

    op.drop_index(
        "idx_tag_assignment_tag", table_name="tag_assignment"
    )
    op.drop_index(
        "idx_tag_assignment_lookup", table_name="tag_assignment"
    )
    op.drop_table("tag_assignment")

    op.drop_index("idx_tag_name", table_name="tag")
    op.drop_table("tag")
