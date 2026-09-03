from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db_session
from app.models.mapping import InstrumentMapping
from app.models.user import User
from app.schemas.mappings import (
    MappingFieldCandidateRead,
    MappingFieldOptionRead,
    MappingReviewDetailRead,
    MappingReviewItemRead,
    MappingReviewRead,
    MappingReviewRowDetailRead,
)
from app.services.mappings import DATE_FORMAT_OPTIONS, get_mapping_label_aliases, refresh_mapping_review_bundle
from app.services.job_constants import MAPPING_AUTO_OPTION, MAPPING_NONE_OPTION
from app.services.workspace_views import build_mapping_review, get_mapping_job, host_label_for_job
from app.ui import router as legacy_ui


router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.get("/current", response_model=MappingReviewRead)
def current_mapping_review(
    job_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MappingReviewRead:
    payload = build_mapping_review(db, current_user=current_user, job_id=job_id)
    return MappingReviewRead(
        job_id=payload["job_id"],
        project_id=payload["project_id"],
        project_title=payload["project_title"],
        host_label=payload["host_label"],
        refresh_decision_pending=bool(payload["refresh_decision_pending"]),
        confirmed_mapping_count=int(payload["confirmed_mapping_count"]),
        rows=[MappingReviewItemRead(**item) for item in payload["rows"]],
    )


@router.get("/review", response_model=MappingReviewDetailRead)
def mapping_review_detail(
    job_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MappingReviewDetailRead:
    job = get_mapping_job(db, current_user=current_user, job_id=job_id)
    if job is None:
        return MappingReviewDetailRead(
            job_id=None,
            job_status=None,
            total_rows=0,
            project_id=None,
            project_title=None,
            host_label=None,
            refresh_decision_pending=False,
            confirmed_mapping_count=0,
            mapping_none_option=MAPPING_NONE_OPTION,
            mapping_auto_option=MAPPING_AUTO_OPTION,
            date_format_options=sorted(DATE_FORMAT_OPTIONS),
            rows=[],
        )

    options = job.options_json if isinstance(job.options_json, dict) else {}
    confirmed_instruments = options.get("mapping_refresh_confirmed_instruments")
    confirmed_mapping_count = len(confirmed_instruments) if isinstance(confirmed_instruments, list) else 0

    if legacy_ui._is_mapping_refresh_prompt_pending(job):
        return MappingReviewDetailRead(
            job_id=job.id,
            job_status=job.status.value,
            total_rows=job.total_rows,
            project_id=job.redcap_project_id,
            project_title=job.redcap_project_title,
            host_label=host_label_for_job(job),
            refresh_decision_pending=True,
            confirmed_mapping_count=confirmed_mapping_count,
            mapping_none_option=MAPPING_NONE_OPTION,
            mapping_auto_option=MAPPING_AUTO_OPTION,
            date_format_options=sorted(DATE_FORMAT_OPTIONS),
            rows=[],
        )

    mapping_rows: list[dict[str, object]] = []
    if job.redcap_project_id:
        validation_summary = job.validation_summary_json if isinstance(job.validation_summary_json, dict) else {}
        alias_bank = get_mapping_label_aliases(db)
        refreshed_summary = refresh_mapping_review_bundle(validation_summary, alias_bank=alias_bank)
        if refreshed_summary.get("instrument_reviews"):
            job.validation_summary_json = refreshed_summary
            validation_summary = refreshed_summary
        project_mappings = db.scalars(
            select(InstrumentMapping).where(
                InstrumentMapping.redcap_host_id == job.redcap_host_id,
                InstrumentMapping.redcap_project_id == job.redcap_project_id,
                InstrumentMapping.instrument_name.in_(validation_summary.get("instrument_sequence", [])),
            )
        ).all()
        mapping_rows = legacy_ui._build_mapping_rows(job, list(project_mappings), alias_bank=alias_bank)

    db.commit()
    return MappingReviewDetailRead(
        job_id=job.id,
        job_status=job.status.value,
        total_rows=job.total_rows,
        project_id=job.redcap_project_id,
        project_title=job.redcap_project_title,
        host_label=host_label_for_job(job),
        refresh_decision_pending=False,
        confirmed_mapping_count=confirmed_mapping_count,
        mapping_none_option=MAPPING_NONE_OPTION,
        mapping_auto_option=MAPPING_AUTO_OPTION,
        date_format_options=sorted(DATE_FORMAT_OPTIONS),
        rows=[
            MappingReviewRowDetailRead(
                mapping_id=row["mapping"].id,
                instrument_name=row["review"]["instrument_name"],
                instrument_label=row["review"]["instrument_label"],
                confidence=row["mapping"].confidence,
                mapping_status=row["mapping"].status,
                notes=list(row["review"].get("notes") or []),
                selected_status_candidate=MappingFieldCandidateRead(**row["review"]["selected_status_candidate"])
                if isinstance(row["review"].get("selected_status_candidate"), dict)
                else None,
                selected_date_candidate=MappingFieldCandidateRead(**row["review"]["selected_date_candidate"])
                if isinstance(row["review"].get("selected_date_candidate"), dict)
                else None,
                status_options=[
                    MappingFieldOptionRead(
                        field_name=option["field_name"],
                        field_label=option.get("field_label"),
                        field_type=option["field_type"],
                        validation_type=option.get("validation_type"),
                    )
                    for option in row["status_options"]
                ],
                date_options=[
                    MappingFieldOptionRead(
                        field_name=option["field_name"],
                        field_label=option.get("field_label"),
                        field_type=option["field_type"],
                        validation_type=option.get("validation_type"),
                    )
                    for option in row["date_options"]
                ],
                selected_status_field_name=row["selected_status_field_name"],
                selected_date_field_name=row["selected_date_field_name"],
                selected_status_lock_value=row["selected_status_lock_value"],
                selected_status_value_help=row["selected_status_value_help"],
                selected_date_format=row["selected_date_format"],
            )
            for row in mapping_rows
        ],
    )
