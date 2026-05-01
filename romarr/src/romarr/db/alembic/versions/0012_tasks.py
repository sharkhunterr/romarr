"""Spec 012 — Tasks & Scheduler schema.

Three tables:

  * ``job`` — operator-configurable schedule + audit columns.
    Factory-default jobs carry ``is_factory_default = true`` so
    the seeder can detect them on subsequent boots and avoid
    overwriting operator edits.
  * ``job_run`` — append-only history. CASCADE on ``job.id``
    delete; user FK SET NULL so deleted-user audit rows
    survive.
  * ``apscheduler_jobs`` — APScheduler's own ``SQLAlchemyJobStore``
    table. Declared here for reproducibility across deployments
    and tests; APScheduler reads/writes it at runtime, Romarr's
    SQLAlchemy models do not map it.

No data seeding in the migration — the runtime seeder
(`romarr.tasks.seeder`) populates the nine factory defaults on
first boot. Keeps the JSON-friendly catalogue separate from
the DDL.

Revision ID: 0012_tasks
Revises: 0011_notifications
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_tasks"
down_revision = "0011_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("schedule_cron", sa.String(), nullable=True),
        sa.Column(
            "schedule_interval_seconds", sa.Integer(), nullable=True
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "next_run_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_run_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_run_duration_ms", sa.Integer(), nullable=True
        ),
        sa.Column("last_run_status", sa.String(16), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "max_concurrent_instances",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "is_factory_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
        sa.CheckConstraint(
            "type IN ("
            "'rss_sync','cutoff_search','missing_search','refresh_metadata',"
            "'dat_update','backup','health_check','library_scan',"
            "'auto_check_added','custom'"
            ")",
            name="ck_job_type",
        ),
        sa.CheckConstraint(
            "last_run_status IS NULL OR "
            "last_run_status IN ('success','failed','partial','cancelled')",
            name="ck_job_last_run_status",
        ),
    )
    op.create_index("idx_job_enabled", "job", ["enabled"])
    op.create_index(
        "idx_job_last_run_status", "job", ["last_run_status"]
    )

    op.create_table(
        "job_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(64),
            sa.ForeignKey("job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "finished_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "items_processed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("output_summary", sa.JSON(), nullable=True),
        sa.Column("triggered_by", sa.String(16), nullable=False),
        sa.Column(
            "triggered_by_user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "cancellation_forced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.CheckConstraint(
            "status IN ('running','success','failed','partial','cancelled')",
            name="ck_job_run_status",
        ),
        sa.CheckConstraint(
            "triggered_by IN ('scheduled','manual','command','event')",
            name="ck_job_run_triggered_by",
        ),
    )
    op.create_index(
        "idx_job_run_job_id_started_at",
        "job_run",
        ["job_id", "started_at"],
    )
    op.create_index(
        "idx_job_run_started_at", "job_run", ["started_at"]
    )
    op.create_index("idx_job_run_status", "job_run", ["status"])

    # APScheduler's own SQLAlchemyJobStore table. Declared here
    # for reproducibility; APScheduler reads/writes it at
    # runtime via its own SQL.
    op.create_table(
        "apscheduler_jobs",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column(
            "next_run_time", sa.Float(precision=25), nullable=True
        ),
        sa.Column("job_state", sa.LargeBinary(), nullable=False),
    )
    op.create_index(
        "ix_apscheduler_jobs_next_run_time",
        "apscheduler_jobs",
        ["next_run_time"],
    )


def downgrade() -> None:
    # Drop in dependency order: APScheduler's table first
    # (it has no FK dependencies), then job_run (FK → job),
    # then job.
    op.drop_index(
        "ix_apscheduler_jobs_next_run_time",
        table_name="apscheduler_jobs",
    )
    op.drop_table("apscheduler_jobs")

    op.drop_index("idx_job_run_status", table_name="job_run")
    op.drop_index("idx_job_run_started_at", table_name="job_run")
    op.drop_index(
        "idx_job_run_job_id_started_at", table_name="job_run"
    )
    op.drop_table("job_run")

    op.drop_index("idx_job_last_run_status", table_name="job")
    op.drop_index("idx_job_enabled", table_name="job")
    op.drop_table("job")
