from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_session
from app.db.session import get_db_session
from app.models.enums import JobStatus
from app.models.session import UserSession
from app.schemas.jobs import JobListItemRead, JobsListRead
from app.ui import router as legacy_ui


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobsListRead)
def list_jobs(
    limit: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_session: UserSession = Depends(get_current_session),
) -> JobsListRead:
    jobs = legacy_ui._list_visible_jobs(db, current_user=current_session.user, limit=limit)
    legacy_ui._ensure_report_records_for_jobs(db, jobs)
    report_map = legacy_ui._get_job_report_map(db, jobs)
    job_rows = legacy_ui._build_job_review_rows(
        jobs,
        db=db,
        user_session_id=current_session.id,
    )
    db.commit()
    return JobsListRead(
        items=[
            JobListItemRead(
                id=row["job"].id,
                job_type=row["job"].job_type,
                status=row["job"].status,
                project_id=row["job"].redcap_project_id,
                project_title=row["job"].redcap_project_title,
                request_file_name=row["job"].request_file_name,
                queries_file_name=row["job"].queries_file_name,
                host_label=row["host_label"],
                total_rows=row["job"].total_rows,
                processed_rows=row["job"].processed_rows,
                locked_rows=row["job"].locked_rows,
                unlocked_rows=row["job"].unlocked_rows,
                ignored_rows=row["job"].ignored_rows,
                blocked_rows=row["job"].blocked_rows,
                failed_rows=row["job"].failed_rows,
                review_count=row["review_count"],
                progress=row["progress"],
                report_id=report_map.get(row["job"].id).id if report_map.get(row["job"].id) is not None else None,
                created_at=row["job"].created_at,
                updated_at=row["job"].updated_at,
                completed_at=row["job"].completed_at,
                status_label=row["status_label"],
                status_tone=row["status_tone"],
                action_kind=row["action_kind"],
                action_label=row["action_label"],
                action_hint=row["action_hint"],
                cancel_label=row["cancel_label"],
                continue_label=row["continue_label"],
                remap_label=row["remap_label"],
                launch_mode=row["launch_mode"],
            )
            for row in job_rows
        ],
        has_active_jobs=any(
            row["job"].status
            in {
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.WAITING_DUE_TO_RATE_LIMIT,
                JobStatus.CANCEL_REQUESTED,
            }
            for row in job_rows
        ),
    )
