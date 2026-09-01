import logging

from app.db.session import SessionLocal
from app.services.job_processing import process_job_in_background
from app.services.maintenance import run_retention_cleanup
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="app.workers.tasks.process_job")
def process_job(
    *,
    job_id: str,
    actor_user_id: str,
    user_session_id: str,
    retry_row_ids: list[str] | None = None,
) -> None:
    from uuid import UUID

    process_job_in_background(
        job_id=UUID(job_id),
        actor_user_id=UUID(actor_user_id),
        user_session_id=UUID(user_session_id),
        retry_row_ids=[UUID(row_id) for row_id in (retry_row_ids or [])],
    )


@celery_app.task(name="app.workers.tasks.run_retention_cleanup")
def run_retention_cleanup_task(*, dry_run: bool = False) -> dict[str, int]:
    with SessionLocal() as db:
        summary = run_retention_cleanup(db, dry_run=dry_run)
        if dry_run:
            db.rollback()
        else:
            db.commit()

    logger.info("Retention cleanup finished: %s", summary.to_dict())
    return summary.to_dict()
