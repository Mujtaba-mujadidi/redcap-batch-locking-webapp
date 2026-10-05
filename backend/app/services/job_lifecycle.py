"""Shared helpers for starting, retrying, and cancelling jobs.

These functions used to live in the UI router. HTTP routes still call them;
this module just gives them a home outside presentation code.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from uuid import UUID

from fastapi import Request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import utc_now
from app.models.enums import EventLevel, JobStatus, ReportType, RowResultStatus
from app.models.job import Job, JobEvent, JobRow, Report, RowResult
from app.services.audit import record_audit_event
from app.services.job_constants import ACTIVE_JOB_STATUSES, REPORTABLE_JOB_STATUSES
from app.services.workspace_views import build_job_report_filename


settings = get_settings()


def format_row_count(count: int) -> str:
    return f"{count} row{'s' if count != 1 else ''}"


def resolve_live_processing_max_rows() -> int:
    return max(int(settings.live_processing_max_rows or 0), 0)


def resolve_processing_mode(*, row_count: int) -> str:
    live_processing_max_rows = resolve_live_processing_max_rows()
    if live_processing_max_rows > 0 and 0 < row_count <= live_processing_max_rows:
        return "live"
    return "background"


def resolve_retry_processing_mode(*, job: Job, row_count: int) -> str:
    runtime_mode = str(get_job_runtime_state(job).get("mode") or "").strip()
    if runtime_mode in {"live", "background"}:
        return runtime_mode
    return resolve_processing_mode(row_count=row_count)


def has_shared_redcap_api_key_cache_secret() -> bool:
    return bool((settings.redcap_api_key_cache_secret or "").strip())


def processing_mode_runtime_phrase(processing_mode: str) -> str:
    # Kept for call-site compatibility; desktop processing only continues while the app is open.
    return "while the app stays open"


def processing_mode_action_label(processing_mode: str) -> str:
    return "processing"


def processing_mode_title(processing_mode: str) -> str:
    return "Processing"


INTERRUPTED_JOB_MESSAGE = (
    "Processing stopped because the app closed or the connection was interrupted. "
    "Resume remaining rows to continue from where it left off."
)


def get_retryable_rows(db: Session, *, job_id: UUID) -> list[JobRow]:
    return list(
        db.scalars(
            select(JobRow)
            .options(selectinload(JobRow.row_result))
            .outerjoin(RowResult, RowResult.job_row_id == JobRow.id)
            .where(JobRow.job_id == job_id)
            .where(
                or_(
                    RowResult.id.is_(None),
                    RowResult.status == RowResultStatus.FAILED,
                    RowResult.status == RowResultStatus.CANCELLED,
                    and_(
                        RowResult.status == RowResultStatus.PENDING,
                        RowResult.processed_at.is_(None),
                    ),
                )
            )
            .order_by(JobRow.row_number)
        ).all()
    )


def summarize_retry_candidates(rows: list[JobRow]) -> dict[str, object]:
    failed_count = 0
    unprocessed_count = 0

    for row in rows:
        row_result = row.row_result
        if row_result is not None and row_result.status == RowResultStatus.FAILED:
            failed_count += 1
        else:
            unprocessed_count += 1

    if unprocessed_count > 0:
        selection_copy = (
            f"{format_row_count(failed_count)} that failed and {format_row_count(unprocessed_count)} that were not processed yet"
            if failed_count > 0
            else f"{format_row_count(unprocessed_count)} that were not processed yet"
        )
        return {
            "count": len(rows),
            "failed_count": failed_count,
            "unprocessed_count": unprocessed_count,
            "retry_scope": "remaining_rows",
            "action_label": "Resume Remaining Rows",
            "selection_copy": selection_copy,
            "progress_summary": "remaining rows",
        }

    return {
        "count": len(rows),
        "failed_count": failed_count,
        "unprocessed_count": 0,
        "retry_scope": "failed_only",
        "action_label": "Retry Failed Rows",
        "selection_copy": f"{format_row_count(failed_count)} that failed",
        "progress_summary": "failed rows",
    }


def mark_unprocessed_rows_as_cancelled(
    db: Session,
    *,
    job_id: UUID,
    reason: str,
    message: str = "Row was not processed because processing stopped early.",
) -> int:
    rows = list(db.scalars(select(JobRow).where(JobRow.job_id == job_id).order_by(JobRow.row_number)).all())
    cancelled_count = 0

    for row in rows:
        row_result = row.row_result
        if row_result is not None and row_result.processed_at is not None:
            continue

        if row_result is None:
            row_result = RowResult(job_row_id=row.id)
            db.add(row_result)

        row_result.status = RowResultStatus.CANCELLED
        row_result.outcome_code = "not_processed"
        row_result.message = message
        row_result.redcap_http_status = None
        row_result.query_blocking_count = None
        row_result.details_json = {
            "job_failure_reason": reason,
            "processing_steps": [
                message,
            ],
        }
        row_result.duration_ms = None
        row_result.processed_at = None
        cancelled_count += 1

    return cancelled_count


def build_job_outcome_copy(job: Job) -> str:
    unprocessed_rows = max((job.total_rows or 0) - (job.processed_rows or 0), 0)

    if job.status == JobStatus.COMPLETED:
        if job.ignored_rows and not job.locked_rows and not job.unlocked_rows:
            verb = "was" if job.ignored_rows == 1 else "were"
            return f"No lock changes were applied. {format_row_count(job.ignored_rows).capitalize()} {verb} skipped."
        if job.ignored_rows:
            verb = "was" if job.ignored_rows == 1 else "were"
            return (
                f"Completed with changes. {format_row_count(job.ignored_rows).capitalize()} {verb} skipped."
            )
        return "Completed successfully."

    if job.failed_rows == 0 and job.blocked_rows > 0:
        return job.last_error_summary or (
            f"{format_row_count(job.blocked_rows).capitalize()} could not run because REDCap reported that the target "
            "form has no existing data yet."
        )

    parts: list[str] = []
    if job.failed_rows:
        parts.append(f"{format_row_count(job.failed_rows).capitalize()} failed.")
    if job.blocked_rows:
        verb = "was" if job.blocked_rows == 1 else "were"
        parts.append(f"{format_row_count(job.blocked_rows).capitalize()} {verb} blocked.")
    if unprocessed_rows:
        verb = "was" if unprocessed_rows == 1 else "were"
        parts.append(f"{format_row_count(unprocessed_rows).capitalize()} {verb} not processed after the run stopped early.")
    if job.last_error_summary:
        parts.append(job.last_error_summary)

    return " ".join(parts) if parts else "Processing failed."


def build_job_result_stats(job: Job) -> list[str]:
    if job.status not in REPORTABLE_JOB_STATUSES and job.processed_rows <= 0:
        return []

    stats: list[str] = []
    if job.locked_rows:
        stats.append(f"{job.locked_rows} locked")
    if job.unlocked_rows:
        stats.append(f"{job.unlocked_rows} unlocked")
    if job.ignored_rows:
        stats.append(f"{job.ignored_rows} skipped")
    if job.blocked_rows:
        stats.append(f"{job.blocked_rows} blocked")
    if job.failed_rows:
        stats.append(f"{job.failed_rows} failed")

    unprocessed_rows = max((job.total_rows or 0) - (job.processed_rows or 0), 0)
    if unprocessed_rows:
        stats.append(f"{unprocessed_rows} not processed")

    return stats


def get_job_runtime_state(job: Job) -> dict[str, object]:
    options = job.options_json if isinstance(job.options_json, dict) else {}
    runtime_state = options.get("runtime")
    return runtime_state if isinstance(runtime_state, dict) else {}


def set_job_runtime_state(job: Job, **updates: object) -> None:
    options = dict(job.options_json) if isinstance(job.options_json, dict) else {}
    runtime_state = dict(options.get("runtime") or {})
    runtime_state.update(updates)
    options["runtime"] = runtime_state
    job.options_json = options


def get_job_worker_task_id(job: Job) -> str | None:
    runtime_state = get_job_runtime_state(job)
    task_id = str(runtime_state.get("worker_task_id") or "").strip()
    return task_id or None


def resolve_job_rate_limit(job: Job) -> int:
    host_limit = job.redcap_host.rate_limit_per_minute if job.redcap_host is not None else None
    resolved_limit = host_limit or settings.redcap_rate_limit_per_minute_default
    return max(1, int(resolved_limit))


def find_active_project_job(db: Session, *, job: Job) -> Job | None:
    statement = select(Job).where(
        Job.id != job.id,
        Job.status.in_(tuple(ACTIVE_JOB_STATUSES)),
    )
    if job.redcap_host_id is not None:
        statement = statement.where(Job.redcap_host_id == job.redcap_host_id)
    else:
        statement = statement.where(Job.redcap_api_url == job.redcap_api_url)

    if job.redcap_project_id:
        statement = statement.where(Job.redcap_project_id == job.redcap_project_id)

    statement = statement.order_by(Job.created_at.asc()).limit(1)
    return db.scalar(statement)


def record_job_event(
    db: Session,
    *,
    job: Job,
    event_type: str,
    level: EventLevel = EventLevel.INFO,
    message: str | None = None,
    job_row_id: UUID | None = None,
    payload_json: dict[str, object] | None = None,
    status_from: JobStatus | None = None,
    status_to: JobStatus | None = None,
) -> None:
    db.add(
        JobEvent(
            job_id=job.id,
            job_row_id=job_row_id,
            level=level,
            event_type=event_type,
            status_from=status_from,
            status_to=status_to,
            message=message,
            payload_json=payload_json,
        )
    )


def recalculate_job_rollups(db: Session, *, job: Job) -> None:
    rows = list(db.scalars(select(JobRow).where(JobRow.job_id == job.id).order_by(JobRow.row_number)).all())
    processed_rows = 0
    locked_rows = 0
    unlocked_rows = 0
    ignored_rows = 0
    blocked_rows = 0
    failed_rows = 0

    for row in rows:
        row_result = row.row_result
        if row_result is None:
            continue
        if row_result.processed_at is not None:
            processed_rows += 1
        if row_result.status == RowResultStatus.SUCCESS:
            if row_result.outcome_code == "locked":
                locked_rows += 1
            elif row_result.outcome_code == "unlocked":
                unlocked_rows += 1
        elif row_result.status == RowResultStatus.IGNORED:
            ignored_rows += 1
        elif row_result.status == RowResultStatus.BLOCKED:
            blocked_rows += 1
        elif row_result.status == RowResultStatus.FAILED:
            failed_rows += 1

    job.processed_rows = processed_rows
    job.locked_rows = locked_rows
    job.unlocked_rows = unlocked_rows
    job.ignored_rows = ignored_rows
    job.blocked_rows = blocked_rows
    job.failed_rows = failed_rows


def load_job_rows_for_report(db: Session, *, job_id: UUID) -> list[JobRow]:
    return list(
        db.scalars(
            select(JobRow)
            .options(selectinload(JobRow.row_result))
            .where(JobRow.job_id == job_id)
            .order_by(JobRow.row_number)
        ).all()
    )


def upsert_job_report(db: Session, *, job: Job, report_bytes: bytes) -> Report:
    report = db.scalar(
        select(Report).where(
            Report.job_id == job.id,
            Report.report_type == ReportType.CSV,
        )
    )
    checksum = hashlib.sha256(report_bytes).hexdigest()
    file_name = build_job_report_filename(job)

    if report is None:
        report = Report(
            job_id=job.id,
            report_type=ReportType.CSV,
            storage_path=f"generated://job/{job.id}/{file_name}",
            file_name=file_name,
            content_type="text/csv",
        )
        db.add(report)

    report.file_name = file_name
    report.content_type = "text/csv"
    report.storage_path = f"generated://job/{job.id}/{file_name}"
    report.byte_size = len(report_bytes)
    report.checksum_sha256 = checksum
    return report


def finalize_job_cancellation(
    db: Session,
    *,
    job: Job,
    previous_status: JobStatus,
    cancellation_message: str,
    row_message: str,
    event_message: str,
    build_report_csv: Callable[[Job, list[JobRow]], bytes],
    actor_user_id: UUID | None = None,
    processing_mode: str | None = None,
    request: Request | None = None,
) -> int:
    cancelled_count = mark_unprocessed_rows_as_cancelled(
        db,
        job_id=job.id,
        reason=cancellation_message,
        message=row_message,
    )
    recalculate_job_rollups(db, job=job)
    job.status = JobStatus.CANCELLED
    job.cancellation_requested_at = job.cancellation_requested_at or utc_now()
    job.completed_at = utc_now()
    job.last_error_summary = cancellation_message
    resolved_mode = str(get_job_runtime_state(job).get("mode") or processing_mode or "background").strip() or "background"
    set_job_runtime_state(
        job,
        mode=resolved_mode,
        phase="cancelled",
        latest_message=cancellation_message,
        rate_limit_wait_until=None,
    )
    record_job_event(
        db,
        job=job,
        event_type="job.cancelled",
        message=event_message,
        status_from=previous_status,
        status_to=JobStatus.CANCELLED,
        payload_json={
            "cancelled_rows": cancelled_count,
            "processing_mode": resolved_mode,
        },
    )
    rows = load_job_rows_for_report(db, job_id=job.id)
    upsert_job_report(db, job=job, report_bytes=build_report_csv(job, rows))
    if actor_user_id is not None:
        record_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="jobs.cancel",
            object_type="job",
            object_id=str(job.id),
            request=request,
            metadata={
                "previous_status": previous_status.value,
                "cancelled_rows": cancelled_count,
                "processing_mode": resolved_mode,
            },
        )
    return cancelled_count


def _minimal_interruption_report(job: Job, rows: list[JobRow]) -> bytes:
    processed = sum(1 for row in rows if row.row_result is not None and row.row_result.processed_at is not None)
    return (
        "Job Status,Total Rows,Processed Rows,Message\n"
        f"interrupted,{job.total_rows or len(rows)},{processed},"
        "Processing was interrupted before all rows finished.\n"
    ).encode("utf-8")


def recover_interrupted_active_jobs(
    db: Session,
    *,
    build_report_csv: Callable[[Job, list[JobRow]], bytes] | None = None,
) -> int:
    """Mark orphaned active jobs as cancelled so users can resume remaining rows.

    Desktop workers live in-process. After an app restart (or crash) any job left in
    queued/running/waiting/cancel_requested has no worker and must be recovered.
    """
    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.status.in_(tuple(ACTIVE_JOB_STATUSES)))
            .order_by(Job.created_at.asc())
        ).all()
    )
    if not jobs:
        return 0

    report_builder = build_report_csv or _minimal_interruption_report
    recovered = 0
    for job in jobs:
        previous_status = job.status
        finalize_job_cancellation(
            db,
            job=job,
            previous_status=previous_status,
            cancellation_message=INTERRUPTED_JOB_MESSAGE,
            row_message="Row was not processed because processing was interrupted before it finished.",
            event_message="Job was interrupted (app closed or connection lost). Remaining rows were left available to resume.",
            build_report_csv=report_builder,
            processing_mode=str(get_job_runtime_state(job).get("mode") or "background"),
        )
        record_job_event(
            db,
            job=job,
            event_type="job.interrupted",
            level=EventLevel.WARNING,
            message=INTERRUPTED_JOB_MESSAGE,
            status_from=previous_status,
            status_to=JobStatus.CANCELLED,
        )
        recovered += 1
    return recovered
