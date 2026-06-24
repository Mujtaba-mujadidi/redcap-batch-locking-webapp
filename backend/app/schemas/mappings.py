from uuid import UUID

from pydantic import BaseModel

from app.models.enums import MappingConfidence, MappingStatus


class MappingReviewItemRead(BaseModel):
    instrument_name: str
    instrument_label: str | None
    confidence: MappingConfidence | None
    mapping_status: MappingStatus | None
    form_complete_field_name: str | None
    status_field_name: str | None
    lock_date_field_name: str | None
    suggested_status_field_name: str | None
    suggested_date_field_name: str | None
    suggested_status_lock_value: str | None
    suggested_date_format: str | None
    requires_confirmation: bool


class MappingReviewRead(BaseModel):
    job_id: UUID | None
    project_id: str | None
    project_title: str | None
    host_label: str | None
    refresh_decision_pending: bool
    confirmed_mapping_count: int
    rows: list[MappingReviewItemRead]
