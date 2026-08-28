from functools import lru_cache
from os import getenv
from secrets import token_urlsafe


class Settings:
    """Centralized runtime settings loaded from environment variables."""

    app_name: str = "REDCap Batch Locking"
    app_version: str = "0.1.0"
    database_url: str = getenv(
        "DATABASE_URL",
        "postgresql+psycopg://redcap_app:redcap_app@localhost:5432/redcap_batch_locking",
    )
    session_cookie_name: str = getenv("SESSION_COOKIE_NAME", "redcap_session")
    session_cookie_secure: bool = getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    session_cookie_samesite: str = getenv("SESSION_COOKIE_SAMESITE", "lax")
    session_cookie_domain: str | None = getenv("SESSION_COOKIE_DOMAIN") or None
    session_ttl_hours: int = int(getenv("SESSION_TTL_HOURS", "12"))
    live_processing_max_rows: int = int(getenv("LIVE_PROCESSING_MAX_ROWS", "200"))
    redcap_api_key_cache_ttl_hours: int = int(getenv("REDCAP_API_KEY_CACHE_TTL_HOURS", "2"))
    redcap_api_key_cache_secret: str = getenv("REDCAP_API_KEY_CACHE_SECRET", "")
    redcap_api_key_cache_ephemeral_secret: str = token_urlsafe(32)
    redcap_rate_limit_per_minute_default: int = int(getenv("REDCAP_RATE_LIMIT_PER_MINUTE_DEFAULT", "300"))
    redis_url: str = getenv("REDIS_URL", "redis://localhost:6379/0")
    celery_broker_url: str = getenv("CELERY_BROKER_URL") or getenv("REDIS_URL", "redis://localhost:6379/0")
    celery_result_backend: str = getenv("CELERY_RESULT_BACKEND") or getenv("REDIS_URL", "redis://localhost:6379/0")
    terminal_job_retention_days: int = int(getenv("TERMINAL_JOB_RETENTION_DAYS", "30"))
    maintenance_cleanup_interval_hours: int = int(getenv("MAINTENANCE_CLEANUP_INTERVAL_HOURS", "24"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
