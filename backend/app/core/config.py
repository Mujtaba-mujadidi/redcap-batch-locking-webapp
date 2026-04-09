from functools import lru_cache
from os import getenv


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
