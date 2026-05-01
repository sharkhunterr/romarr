"""SQLAlchemy models for the tasks/scheduler feature (spec 012).

Two tables:

  * ``job`` — operator-configurable schedule + audit columns.
    Factory-default jobs carry ``is_factory_default = true`` so
    the seeder can detect them on subsequent boots and avoid
    overwriting operator edits.
  * ``job_run`` — append-only history. One row per execution;
    ``running`` is the initial state, transitioned to a terminal
    state when the runner returns or shutdown forces it.

The third table the spec mandates (``apscheduler_jobs``) is
declared in the migration but NOT mapped here — APScheduler
owns it at runtime.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_JOB_TYPE_CHECK = (
    "type IN ("
    "'rss_sync','cutoff_search','missing_search','refresh_metadata',"
    "'dat_update','backup','health_check','library_scan',"
    "'auto_check_added','custom'"
    ")"
)
_JOB_LAST_RUN_STATUS_CHECK = (
    "last_run_status IS NULL OR "
    "last_run_status IN ('success','failed','partial','cancelled')"
)
_JOB_RUN_STATUS_CHECK = (
    "status IN ('running','success','failed','partial','cancelled')"
)
_JOB_RUN_TRIGGER_CHECK = (
    "triggered_by IN ('scheduled','manual','command','event')"
)


class Job(Base, TimestampMixin):
    """One operator-configurable scheduled / event-driven job.

    The ``id`` is a TEXT PK that matches APScheduler's ``job_id``
    (e.g. ``MissingSearch``) — APScheduler uses it to look up
    the in-memory dispatch entry. The PK is intentionally not
    auto-incremented.
    """

    __tablename__ = "job"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)

    schedule_cron: Mapped[str | None] = mapped_column(String, nullable=True)
    schedule_interval_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_run_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)

    max_concurrent_instances: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    max_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )
    is_factory_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        CheckConstraint(_JOB_TYPE_CHECK, name="ck_job_type"),
        CheckConstraint(
            _JOB_LAST_RUN_STATUS_CHECK, name="ck_job_last_run_status"
        ),
        Index("idx_job_enabled", "enabled"),
        Index("idx_job_last_run_status", "last_run_status"),
    )


class JobRun(Base):
    """Append-only history row. CASCADE on ``job.id`` delete so
    deleting a job removes its history too. The user FK is SET
    NULL because user accounts can outlive their triggers and
    we'd rather keep the audit attribution as anonymous than
    refuse the delete.
    """

    __tablename__ = "job_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("job.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    items_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    output_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    triggered_by: Mapped[str] = mapped_column(String(16), nullable=False)
    triggered_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancellation_forced: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        CheckConstraint(_JOB_RUN_STATUS_CHECK, name="ck_job_run_status"),
        CheckConstraint(
            _JOB_RUN_TRIGGER_CHECK, name="ck_job_run_triggered_by"
        ),
        Index("idx_job_run_job_id_started_at", "job_id", "started_at"),
        Index("idx_job_run_started_at", "started_at"),
        Index("idx_job_run_status", "status"),
    )


__all__ = ["Job", "JobRun"]
