from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EventLevel, JobStatus, JobType, ReportType, RowAction, RowResultStatus
from app.models.types import enum_type


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_owner_status_created_at", "owner_id", "status", "created_at"),
        Index("ix_jobs_project_status", "redcap_project_id", "status"),
    )

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    redcap_host_id: Mapped[UUID | None] = mapped_column(ForeignKey("redcap_hosts.id", ondelete="SET NULL"))
    job_type: Mapped[JobType] = mapped_column(enum_type(JobType, "job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        enum_type(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.DRAFT,
        server_default=text(f"'{JobStatus.DRAFT.value}'"),
    )
    redcap_api_url: Mapped[str] = mapped_column(Text, nullable=False)
    redcap_project_id: Mapped[str | None] = mapped_column(String(100))
    redcap_project_title: Mapped[str | None] = mapped_column(String(255))
    request_file_name: Mapped[str | None] = mapped_column(String(255))
    queries_file_name: Mapped[str | None] = mapped_column(String(255))
    source_file_checksum: Mapped[str | None] = mapped_column(String(64))
    options_json: Mapped[dict | None] = mapped_column(JSON)
    validation_summary_json: Mapped[dict | None] = mapped_column(JSON)
    last_error_summary: Mapped[str | None] = mapped_column(Text)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    unlocked_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    ignored_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    blocked_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    retried_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner = relationship("User", back_populates="owned_jobs")
    redcap_host = relationship("REDCapHost", back_populates="jobs")
    rows = relationship("JobRow", back_populates="job", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="job", cascade="all, delete-orphan")
    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan")


class JobRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_rows"
    __table_args__ = (
        UniqueConstraint("job_id", "row_number", name="uq_job_rows_job_id_row_number"),
        Index("ix_job_rows_job_id_record_id", "job_id", "record_id"),
        Index("ix_job_rows_job_id_target_instrument", "job_id", "target_instrument"),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[RowAction] = mapped_column(enum_type(RowAction, "row_action"), nullable=False)
    record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_name: Mapped[str | None] = mapped_column(String(255))
    arm_name: Mapped[str | None] = mapped_column(String(255))
    repeat_instance: Mapped[int | None] = mapped_column(Integer)
    repeat_instrument: Mapped[str | None] = mapped_column(String(255))
    target_instrument: Mapped[str] = mapped_column(String(255), nullable=False)
    target_field_name: Mapped[str | None] = mapped_column(String(255))
    input_payload_json: Mapped[dict | None] = mapped_column(JSON)
    has_unresolved_queries: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    job = relationship("Job", back_populates="rows")
    row_result = relationship("RowResult", back_populates="job_row", uselist=False, cascade="all, delete-orphan")
    job_events = relationship("JobEvent", back_populates="job_row")


class RowResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "row_results"
    __table_args__ = (
        UniqueConstraint("job_row_id", name="uq_row_results_job_row_id"),
        Index("ix_row_results_status", "status"),
    )

    job_row_id: Mapped[UUID] = mapped_column(ForeignKey("job_rows.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[RowResultStatus] = mapped_column(
        enum_type(RowResultStatus, "row_result_status"),
        nullable=False,
        default=RowResultStatus.PENDING,
        server_default=text(f"'{RowResultStatus.PENDING.value}'"),
    )
    outcome_code: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    redcap_http_status: Mapped[int | None] = mapped_column(Integer)
    query_blocking_count: Mapped[int | None] = mapped_column(Integer)
    details_json: Mapped[dict | None] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job_row = relationship("JobRow", back_populates="row_result")


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_job_id_report_type", "job_id", "report_type"),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    report_type: Mapped[ReportType] = mapped_column(enum_type(ReportType, "report_type"), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(Integer)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job = relationship("Job", back_populates="reports")


class JobEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "job_events"
    __table_args__ = (
        Index("ix_job_events_job_id_created_at", "job_id", "created_at"),
        Index("ix_job_events_event_type", "event_type"),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    job_row_id: Mapped[UUID | None] = mapped_column(ForeignKey("job_rows.id", ondelete="SET NULL"))
    level: Mapped[EventLevel] = mapped_column(
        enum_type(EventLevel, "event_level"),
        nullable=False,
        default=EventLevel.INFO,
        server_default=text(f"'{EventLevel.INFO.value}'"),
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status_from: Mapped[JobStatus | None] = mapped_column(enum_type(JobStatus, "job_status_transition_from"))
    status_to: Mapped[JobStatus | None] = mapped_column(enum_type(JobStatus, "job_status_transition_to"))
    message: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    job = relationship("Job", back_populates="events")
    job_row = relationship("JobRow", back_populates="job_events")
