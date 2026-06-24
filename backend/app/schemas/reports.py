from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import JobStatus


class ReportListItemRead(BaseModel):
    report_id: UUID
    job_id: UUID
    file_name: str
    content_type: str
    byte_size: int | None
    checksum_sha256: str | None
    job_status: JobStatus
    project_id: str | None
    project_title: str | None
    request_file_name: str | None
    host_label: str
    updated_at: datetime


class ReportsListRead(BaseModel):
    items: list[ReportListItemRead]
