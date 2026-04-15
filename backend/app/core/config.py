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
    redcap_api_key_cache_ttl_hours: int = int(getenv("REDCAP_API_KEY_CACHE_TTL_HOURS", "2"))
    redcap_api_key_cache_secret: str = getenv("REDCAP_API_KEY_CACHE_SECRET", "")
    redcap_api_key_cache_ephemeral_secret: str = token_urlsafe(32)
    redcap_rate_limit_per_minute_default: int = int(getenv("REDCAP_RATE_LIMIT_PER_MINUTE_DEFAULT", "300"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
