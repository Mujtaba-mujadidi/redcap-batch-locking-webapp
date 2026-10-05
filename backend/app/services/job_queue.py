from __future__ import annotations

from uuid import UUID

from app.services.desktop_worker import (
    enqueue_desktop_job_processing,
    is_desktop_job_worker_alive,
    revoke_desktop_job_processing,
)


def enqueue_job_processing(
    *,
    job_id: UUID,
    actor_user_id: UUID,
    user_session_id: UUID,
    retry_row_ids: list[UUID] | None = None,
    task_id: str | None = None,
):
    return enqueue_desktop_job_processing(
        job_id=job_id,
        actor_user_id=actor_user_id,
        user_session_id=user_session_id,
        retry_row_ids=retry_row_ids,
        task_id=task_id,
    )


def revoke_job_processing(task_id: str) -> None:
    revoke_desktop_job_processing(task_id)


def is_job_worker_alive(task_id: str | None) -> bool:
    return is_desktop_job_worker_alive(task_id)
