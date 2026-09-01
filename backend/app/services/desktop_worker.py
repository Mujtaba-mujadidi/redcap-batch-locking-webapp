from __future__ import annotations

import logging
import threading
from uuid import UUID

from app.services.job_processing import process_job_in_background

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cancelled_task_ids: set[str] = set()
_active_threads: dict[str, threading.Thread] = {}


def enqueue_desktop_job_processing(
    *,
    job_id: UUID,
    actor_user_id: UUID,
    user_session_id: UUID,
    retry_row_ids: list[UUID] | None = None,
    task_id: str | None = None,
) -> str:
    resolved_task_id = task_id or f"desktop-{job_id}"

    def _run() -> None:
        with _lock:
            if resolved_task_id in _cancelled_task_ids:
                logger.info("Skipped desktop job %s because task %s was revoked before start.", job_id, resolved_task_id)
                return
        try:
            process_job_in_background(
                job_id=job_id,
                actor_user_id=actor_user_id,
                user_session_id=user_session_id,
                retry_row_ids=retry_row_ids,
            )
        except Exception:
            logger.exception("Desktop background job failed for job_id=%s", job_id)
        finally:
            with _lock:
                _active_threads.pop(resolved_task_id, None)

    thread = threading.Thread(
        target=_run,
        name=f"desktop-job-{job_id}",
        daemon=True,
    )
    with _lock:
        _cancelled_task_ids.discard(resolved_task_id)
        _active_threads[resolved_task_id] = thread
    thread.start()
    return resolved_task_id


def revoke_desktop_job_processing(task_id: str) -> None:
    with _lock:
        _cancelled_task_ids.add(task_id)
        _active_threads.pop(task_id, None)
