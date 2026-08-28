from datetime import timedelta

from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "redcap_batch_locking",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

beat_schedule: dict[str, dict[str, object]] = {}
if settings.maintenance_cleanup_interval_hours > 0:
    beat_schedule["retention-cleanup"] = {
        "task": "app.workers.tasks.run_retention_cleanup",
        "schedule": timedelta(hours=settings.maintenance_cleanup_interval_hours),
    }

celery_app.conf.update(
    task_default_queue="redcap_jobs",
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
    beat_schedule=beat_schedule,
)
