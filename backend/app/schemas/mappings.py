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


class MappingFieldOptionRead(BaseModel):
    field_name: str
    field_label: str | None
    field_type: str
    validation_type: str | None = None


class MappingFieldCandidateRead(BaseModel):
    field_name: str
    field_label: str | None
    field_type: str
    lock_value: str | None = None
    date_format: str | None = None
    validation_type: str | None = None
    note: str | None = None


class MappingReviewRowDetailRead(BaseModel):
    mapping_id: UUID
    instrument_name: str
    instrument_label: str
    confidence: MappingConfidence
    mapping_status: MappingStatus
    notes: list[str]
    selected_status_candidate: MappingFieldCandidateRead | None
    selected_date_candidate: MappingFieldCandidateRead | None
    status_options: list[MappingFieldOptionRead]
    date_options: list[MappingFieldOptionRead]
    selected_status_field_name: str
    selected_date_field_name: str
    selected_status_lock_value: str
    selected_status_value_help: str | None
    selected_date_format: str


class MappingReviewDetailRead(BaseModel):
    job_id: UUID | None
    job_status: str | None
    total_rows: int
    project_id: str | None
    project_title: str | None
    host_label: str | None
    refresh_decision_pending: bool
    confirmed_mapping_count: int
    mapping_none_option: str
    mapping_auto_option: str
    date_format_options: list[str]
    rows: list[MappingReviewRowDetailRead]
