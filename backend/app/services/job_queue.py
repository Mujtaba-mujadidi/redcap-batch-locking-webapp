from __future__ import annotations

import logging
from uuid import UUID

from app.core.config import get_settings
from app.services.desktop_worker import enqueue_desktop_job_processing, revoke_desktop_job_processing

logger = logging.getLogger(__name__)
settings = get_settings()


def enqueue_job_processing(
    *,
    job_id: UUID,
    actor_user_id: UUID,
    user_session_id: UUID,
    retry_row_ids: list[UUID] | None = None,
    task_id: str | None = None,
):
    if settings.is_desktop:
        return enqueue_desktop_job_processing(
            job_id=job_id,
            actor_user_id=actor_user_id,
            user_session_id=user_session_id,
            retry_row_ids=retry_row_ids,
            task_id=task_id,
        )

    from app.workers.tasks import process_job

    return process_job.apply_async(
        kwargs={
            "job_id": str(job_id),
            "actor_user_id": str(actor_user_id),
            "user_session_id": str(user_session_id),
            "retry_row_ids": [str(row_id) for row_id in (retry_row_ids or [])],
        },
        task_id=task_id,
    )


def revoke_job_processing(task_id: str) -> None:
    if settings.is_desktop:
        revoke_desktop_job_processing(task_id)
        return

    from app.workers.celery_app import celery_app

    celery_app.control.revoke(task_id)
