from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import utc_now
from app.models.audit import AuditEvent
from app.models.enums import JobStatus, MappingConfidence, MappingStatus, ReportType, Role
from app.models.job import Job, Report
from app.models.mapping import InstrumentMapping
from app.models.redcap import REDCapHost
from app.models.session import UserSession
from app.models.user import User


settings = get_settings()

MAX_FILENAME_LENGTH = 255
ACTIVE_JOB_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.WAITING_DUE_TO_RATE_LIMIT,
    JobStatus.CANCEL_REQUESTED,
}
JOBS_VISIBLE_STATUSES = (
    JobStatus.AWAITING_MAPPING_CONFIRMATION,
    JobStatus.READY,
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.WAITING_DUE_TO_RATE_LIMIT,
    JobStatus.CANCEL_REQUESTED,
    JobStatus.CANCELLED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_ERRORS,
    JobStatus.FAILED,
)
REPORTABLE_JOB_STATUSES = {
    JobStatus.CANCELLED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_ERRORS,
    JobStatus.FAILED,
}


def can_manage_users(user: User) -> bool:
    return user.role in (Role.ADMIN, Role.SUPER_ADMIN)


def build_dashboard_summary(db: Session, *, current_user: User) -> dict[str, object]:
    now = utc_now()
    return {
        "current_user": current_user,
        "permissions": {
            "can_manage_users": can_manage_users(current_user),
            "can_manage_admins": current_user.role == Role.SUPER_ADMIN,
        },
        "stats": {
            "users": db.scalar(select(func.count()).select_from(User)) or 0,
            "super_admins": db.scalar(
                select(func.count()).select_from(User).where(User.role == Role.SUPER_ADMIN)
            )
            or 0,
            "active_sessions": db.scalar(
                select(func.count())
                .select_from(UserSession)
                .where(UserSession.revoked_at.is_(None), UserSession.expires_at > now)
            )
            or 0,
            "jobs": db.scalar(select(func.count()).select_from(Job)) or 0,
            "reports": db.scalar(select(func.count()).select_from(Report)) or 0,
            "mappings": db.scalar(select(func.count()).select_from(InstrumentMapping)) or 0,
            "audit_events": db.scalar(select(func.count()).select_from(AuditEvent)) or 0,
        },
    }


def list_visible_jobs(
    db: Session,
    *,
    current_user: User,
    limit: int | None = None,
) -> list[Job]:
    statement = (
        select(Job)
        .options(selectinload(Job.redcap_host))
        .where(Job.status.in_(JOBS_VISIBLE_STATUSES))
        .order_by(Job.updated_at.desc())
    )
    if current_user.role == Role.USER:
        statement = statement.where(Job.owner_id == current_user.id)
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.scalars(statement).all())


def ensure_report_records_for_jobs(db: Session, jobs: list[Job]) -> int:
    created_count = 0
    for job in jobs:
        if job.status not in REPORTABLE_JOB_STATUSES:
            continue

        report = db.scalar(
            select(Report).where(
                Report.job_id == job.id,
                Report.report_type == ReportType.CSV,
            )
        )
        if report is not None:
            continue

        file_name = build_job_report_filename(job)
        db.add(
            Report(
                job_id=job.id,
                report_type=ReportType.CSV,
                storage_path=f"generated://job/{job.id}/{file_name}",
                file_name=file_name,
                content_type="text/csv",
            )
        )
        created_count += 1

    return created_count


def build_jobs_list(
    db: Session,
    *,
    current_user: User,
    limit: int | None = None,
) -> dict[str, object]:
    jobs = list_visible_jobs(db, current_user=current_user, limit=limit)
    ensure_report_records_for_jobs(db, jobs)
    report_map = _get_job_report_map(db, jobs)
    items = [
        {
            "id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "project_id": job.redcap_project_id,
            "project_title": job.redcap_project_title,
            "request_file_name": job.request_file_name,
            "queries_file_name": job.queries_file_name,
            "host_label": host_label_for_job(job),
            "total_rows": job.total_rows,
            "processed_rows": job.processed_rows,
            "locked_rows": job.locked_rows,
            "unlocked_rows": job.unlocked_rows,
            "ignored_rows": job.ignored_rows,
            "blocked_rows": job.blocked_rows,
            "failed_rows": job.failed_rows,
            "review_count": len(get_review_instruments(job)),
            "progress": summarize_job_progress(job),
            "report_id": report_map.get(job.id).id if job.id in report_map else None,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "completed_at": job.completed_at,
        }
        for job in jobs
    ]
    return {
        "items": items,
        "has_active_jobs": any(job.status in ACTIVE_JOB_STATUSES for job in jobs),
    }


def build_reports_list(
    db: Session,
    *,
    current_user: User,
) -> list[dict[str, object]]:
    jobs = list_visible_jobs(db, current_user=current_user, limit=None)
    ensure_report_records_for_jobs(db, jobs)

    statement = (
        select(Report)
        .options(selectinload(Report.job).selectinload(Job.redcap_host))
        .join(Job, Report.job_id == Job.id)
        .where(Report.report_type == ReportType.CSV)
        .order_by(Job.updated_at.desc())
    )
    if current_user.role == Role.USER:
        statement = statement.where(Job.owner_id == current_user.id)

    reports = list(db.scalars(statement).all())
    return [
        {
            "report_id": report.id,
            "job_id": report.job_id,
            "file_name": report.file_name,
            "content_type": report.content_type,
            "byte_size": report.byte_size,
            "checksum_sha256": report.checksum_sha256,
            "job_status": report.job.status,
            "project_id": report.job.redcap_project_id,
            "project_title": report.job.redcap_project_title,
            "request_file_name": report.job.request_file_name,
            "host_label": host_label_for_job(report.job),
            "updated_at": report.job.updated_at,
        }
        for report in reports
    ]


def build_mapping_review(
    db: Session,
    *,
    current_user: User,
    job_id: UUID | None = None,
) -> dict[str, object]:
    job = get_mapping_job(db, current_user=current_user, job_id=job_id)
    if job is None:
        return {
            "job_id": None,
            "project_id": None,
            "project_title": None,
            "host_label": None,
            "refresh_decision_pending": False,
            "confirmed_mapping_count": 0,
            "rows": [],
        }

    validation_summary = job.validation_summary_json if isinstance(job.validation_summary_json, dict) else {}
    instrument_sequence = validation_summary.get("instrument_sequence", [])
    review_lookup = validation_summary.get("instrument_reviews", {})
    options = job.options_json if isinstance(job.options_json, dict) else {}

    project_mappings: list[InstrumentMapping] = []
    if job.redcap_project_id and instrument_sequence:
        project_mappings = list(
            db.scalars(
                select(InstrumentMapping).where(
                    InstrumentMapping.redcap_host_id == job.redcap_host_id,
                    InstrumentMapping.redcap_project_id == job.redcap_project_id,
                    InstrumentMapping.instrument_name.in_(instrument_sequence),
                )
            ).all()
        )
    mapping_lookup = {mapping.instrument_name: mapping for mapping in project_mappings}

    rows: list[dict[str, object]] = []
    for instrument_name in instrument_sequence:
        review = review_lookup.get(instrument_name)
        if not isinstance(review, dict) or not review.get("requires_confirmation"):
            continue

        mapping = mapping_lookup.get(instrument_name)
        selected_status = review.get("selected_status_candidate") if isinstance(review.get("selected_status_candidate"), dict) else {}
        selected_date = review.get("selected_date_candidate") if isinstance(review.get("selected_date_candidate"), dict) else {}

        rows.append(
            {
                "instrument_name": instrument_name,
                "instrument_label": review.get("instrument_label"),
                "confidence": _coerce_mapping_confidence(review.get("confidence")),
                "mapping_status": mapping.status if mapping is not None else None,
                "form_complete_field_name": mapping.form_complete_field_name if mapping is not None else None,
                "status_field_name": mapping.crf_status_field_name if mapping is not None else None,
                "lock_date_field_name": mapping.lock_date_field_name if mapping is not None else None,
                "suggested_status_field_name": selected_status.get("field_name"),
                "suggested_date_field_name": selected_date.get("field_name"),
                "suggested_status_lock_value": selected_status.get("lock_value"),
                "suggested_date_format": selected_date.get("date_format"),
                "requires_confirmation": True,
            }
        )

    confirmed_instruments = options.get("mapping_refresh_confirmed_instruments")
    confirmed_mapping_count = len(confirmed_instruments) if isinstance(confirmed_instruments, list) else 0

    return {
        "job_id": job.id,
        "project_id": job.redcap_project_id,
        "project_title": job.redcap_project_title,
        "host_label": host_label_for_job(job),
        "refresh_decision_pending": bool(options.get("mapping_refresh_prompt_pending")),
        "confirmed_mapping_count": confirmed_mapping_count,
        "rows": rows,
    }


def get_mapping_job(
    db: Session,
    *,
    current_user: User,
    job_id: UUID | None = None,
) -> Job | None:
    if job_id is not None:
        job = db.get(Job, job_id)
        if job is None:
            return None
        if current_user.role == Role.USER and job.owner_id != current_user.id:
            return None
        return job

    statement = (
        select(Job)
        .options(selectinload(Job.redcap_host))
        .where(Job.status == JobStatus.AWAITING_MAPPING_CONFIRMATION)
        .order_by(Job.created_at.desc())
    )
    if current_user.role == Role.USER:
        statement = statement.where(Job.owner_id == current_user.id)
    return db.scalar(statement.limit(1))


def get_review_instruments(job: Job) -> list[str]:
    validation_summary = job.validation_summary_json if isinstance(job.validation_summary_json, dict) else {}
    instrument_sequence = validation_summary.get("instrument_sequence", [])
    review_lookup = validation_summary.get("instrument_reviews", {})
    return [
        instrument_name
        for instrument_name in instrument_sequence
        if isinstance(review_lookup.get(instrument_name), dict) and review_lookup[instrument_name].get("requires_confirmation")
    ]


def host_label_for_job(job: Job) -> str:
    return (
        (job.redcap_host.display_name if job.redcap_host is not None else None)
        or urlparse(job.redcap_api_url).netloc
        or job.redcap_api_url
    )


def summarize_job_progress(job: Job) -> dict[str, object]:
    runtime_state = _runtime_state(job)
    total_rows = max(int(runtime_state.get("active_row_count") or job.total_rows or 0), 0)
    processed_rows = max(job.processed_rows, 0)
    progress_percent = int((processed_rows / total_rows) * 100) if total_rows else 0
    processing_mode = str(runtime_state.get("mode") or "background").strip() or "background"
    latest_message = str(runtime_state.get("latest_message") or "").strip()
    wait_until = _parse_runtime_timestamp(runtime_state.get("rate_limit_wait_until"))
    wait_seconds_remaining: int | None = None
    wait_message: str | None = None
    if wait_until is not None:
        wait_seconds_remaining = max(0, int((wait_until - utc_now()).total_seconds()))
        if wait_seconds_remaining > 0:
            wait_message = f"Rate limit reached. Resuming in about {wait_seconds_remaining} seconds."

    if not latest_message:
        if job.status == JobStatus.QUEUED:
            latest_message = "Queued for background processing."
        elif job.status == JobStatus.RUNNING:
            latest_message = "Processing rows now."
        elif job.status == JobStatus.CANCEL_REQUESTED:
            latest_message = "Cancellation requested. Waiting for the current step to finish."
        elif job.status == JobStatus.WAITING_DUE_TO_RATE_LIMIT:
            latest_message = "Paused because the REDCap API rate limit was reached."

    summary_copy = f"{processed_rows} of {total_rows} rows processed" if total_rows else "No rows queued"
    detail_parts = []
    if job.locked_rows:
        detail_parts.append(f"{job.locked_rows} locked")
    if job.unlocked_rows:
        detail_parts.append(f"{job.unlocked_rows} unlocked")
    if job.ignored_rows:
        detail_parts.append(f"{job.ignored_rows} skipped")
    if job.blocked_rows:
        detail_parts.append(f"{job.blocked_rows} blocked")
    if job.failed_rows:
        detail_parts.append(f"{job.failed_rows} failed")

    return {
        "percent": progress_percent,
        "summary": summary_copy,
        "detail": ", ".join(detail_parts),
        "message": latest_message or None,
        "wait_message": wait_message,
        "wait_seconds_remaining": wait_seconds_remaining,
        "mode": processing_mode,
        "rate_limit_per_minute": int(runtime_state.get("rate_limit_per_minute") or _resolve_job_rate_limit(job)),
    }


def build_job_report_filename(job: Job) -> str:
    source_name = job.request_file_name or f"job-{job.id}"
    sanitized_name = sanitize_filename(source_name)
    stem = Path(sanitized_name).stem or f"job-{job.id}"
    return f"{stem}-report.csv"


def sanitize_filename(filename: str) -> str:
    cleaned_filename = Path(filename.strip()).name
    if not cleaned_filename:
        return "job-export.csv"

    cleaned_filename = re.sub(r"[^A-Za-z0-9._ -]", "_", cleaned_filename)
    cleaned_filename = cleaned_filename.lstrip(".")[:MAX_FILENAME_LENGTH].strip()
    return cleaned_filename or "job-export.csv"


def _runtime_state(job: Job) -> dict[str, object]:
    options = job.options_json if isinstance(job.options_json, dict) else {}
    runtime_state = options.get("runtime")
    return runtime_state if isinstance(runtime_state, dict) else {}


def _parse_runtime_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _resolve_job_rate_limit(job: Job) -> int:
    host_limit = job.redcap_host.rate_limit_per_minute if isinstance(job.redcap_host, REDCapHost) else None
    resolved_limit = host_limit or settings.redcap_rate_limit_per_minute_default
    return max(1, int(resolved_limit))


def _get_job_report_map(db: Session, jobs: list[Job]) -> dict[UUID, Report]:
    if not jobs:
        return {}

    reports = list(
        db.scalars(
            select(Report)
            .where(
                Report.job_id.in_([job.id for job in jobs]),
                Report.report_type == ReportType.CSV,
            )
            .order_by(Report.created_at.desc())
        ).all()
    )
    report_map: dict[UUID, Report] = {}
    for report in reports:
        report_map.setdefault(report.job_id, report)
    return report_map


def _coerce_mapping_confidence(value: object) -> MappingConfidence | None:
    if isinstance(value, MappingConfidence):
        return value
    if isinstance(value, str):
        try:
            return MappingConfidence(value)
        except ValueError:
            return None
    return None
