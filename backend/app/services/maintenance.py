from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utc_now
from app.models.audit import AuditEvent
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.redcap_api_key_cache import REDCapApiKeyCache
from app.models.session import UserSession


TERMINAL_JOB_STATUSES = (
    JobStatus.CANCELLED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_ERRORS,
    JobStatus.FAILED,
)


@dataclass
class CleanupSummary:
    expired_api_key_cache_entries: int = 0
    expired_user_sessions: int = 0
    terminal_jobs: int = 0
    old_audit_events: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def run_retention_cleanup(
    db: Session,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
) -> CleanupSummary:
    settings = get_settings()
    current_time = now or utc_now()
    summary = CleanupSummary()

    summary.expired_api_key_cache_entries = _count_expired_api_key_cache_entries(db, now=current_time)
    summary.expired_user_sessions = _count_expired_user_sessions(db, now=current_time)
    summary.terminal_jobs = _count_terminal_jobs_past_retention(
        db,
        now=current_time,
        retention_days=settings.terminal_job_retention_days,
    )
    summary.old_audit_events = _count_old_audit_events(
        db,
        now=current_time,
        job_retention_days=settings.terminal_job_retention_days,
    )

    if dry_run:
        return summary

    if summary.expired_api_key_cache_entries:
        db.execute(delete(REDCapApiKeyCache).where(REDCapApiKeyCache.expires_at <= current_time))

    if summary.expired_user_sessions:
        db.execute(
            delete(UserSession).where(
                or_(
                    UserSession.expires_at <= current_time,
                    UserSession.revoked_at.is_not(None),
                )
            )
        )

    if summary.terminal_jobs:
        db.execute(
            delete(Job).where(
                Job.status.in_(TERMINAL_JOB_STATUSES),
                func.coalesce(Job.completed_at, Job.updated_at, Job.created_at)
                <= current_time - timedelta(days=max(settings.terminal_job_retention_days, 1)),
            )
        )

    if summary.old_audit_events:
        db.execute(
            delete(AuditEvent).where(
                AuditEvent.created_at
                <= current_time - timedelta(days=max(settings.terminal_job_retention_days, 1))
            )
        )

    return summary


def _count_expired_api_key_cache_entries(db: Session, *, now: datetime) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(REDCapApiKeyCache)
            .where(REDCapApiKeyCache.expires_at <= now)
        )
        or 0
    )


def _count_expired_user_sessions(db: Session, *, now: datetime) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(
                or_(
                    UserSession.expires_at <= now,
                    UserSession.revoked_at.is_not(None),
                )
            )
        )
        or 0
    )


def _count_terminal_jobs_past_retention(
    db: Session,
    *,
    now: datetime,
    retention_days: int,
) -> int:
    if retention_days <= 0:
        return 0

    cutoff = now - timedelta(days=retention_days)
    return int(
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.status.in_(TERMINAL_JOB_STATUSES),
                func.coalesce(Job.completed_at, Job.updated_at, Job.created_at) <= cutoff,
            )
        )
        or 0
    )


def _count_old_audit_events(
    db: Session,
    *,
    now: datetime,
    job_retention_days: int,
) -> int:
    if job_retention_days <= 0:
        return 0

    cutoff = now - timedelta(days=job_retention_days)
    return int(
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.created_at <= cutoff)
        )
        or 0
    )
