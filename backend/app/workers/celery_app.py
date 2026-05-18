from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "redcap_batch_locking",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_default_queue="redcap_jobs",
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
)
