from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import JobStatus, JobType


class JobProgressRead(BaseModel):
    percent: int
    summary: str
    detail: str
    message: str | None
    wait_message: str | None
    wait_seconds_remaining: int | None
    mode: str
    rate_limit_per_minute: int


class JobListItemRead(BaseModel):
    id: UUID
    job_type: JobType
    status: JobStatus
    project_id: str | None
    project_title: str | None
    request_file_name: str | None
    queries_file_name: str | None
    host_label: str
    total_rows: int
    processed_rows: int
    locked_rows: int
    unlocked_rows: int
    ignored_rows: int
    blocked_rows: int
    failed_rows: int
    review_count: int
    progress: JobProgressRead
    report_id: UUID | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    status_label: str
    status_tone: str
    action_kind: str | None
    action_label: str | None
    action_hint: str
    cancel_label: str | None
    continue_label: str | None
    remap_label: str | None
    launch_mode: str | None


class JobsListRead(BaseModel):
    items: list[JobListItemRead]
    has_active_jobs: bool
