from __future__ import annotations

import base64
import hashlib
from datetime import timedelta
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utc_now
from app.models.redcap_api_key_cache import REDCapApiKeyCache


def _get_fernet() -> Fernet:
    settings = get_settings()
    secret = settings.redcap_api_key_cache_secret or settings.redcap_api_key_cache_ephemeral_secret
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(derived_key)


def _build_expiry():
    settings = get_settings()
    return utc_now() + timedelta(hours=settings.redcap_api_key_cache_ttl_hours)


def _fingerprint_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:24]


def store_redcap_api_key(
    db: Session,
    *,
    user_session_id: UUID,
    redcap_host_id: UUID,
    api_key: str,
) -> REDCapApiKeyCache:
    cache_entry = db.scalar(
        select(REDCapApiKeyCache).where(
            REDCapApiKeyCache.user_session_id == user_session_id,
            REDCapApiKeyCache.redcap_host_id == redcap_host_id,
        )
    )
    encrypted_api_key = _get_fernet().encrypt(api_key.encode("utf-8")).decode("utf-8")
    if cache_entry is None:
        cache_entry = REDCapApiKeyCache(
            user_session_id=user_session_id,
            redcap_host_id=redcap_host_id,
            encrypted_api_key=encrypted_api_key,
            key_fingerprint=_fingerprint_api_key(api_key),
            expires_at=_build_expiry(),
            last_used_at=utc_now(),
        )
        db.add(cache_entry)
        return cache_entry

    cache_entry.encrypted_api_key = encrypted_api_key
    cache_entry.key_fingerprint = _fingerprint_api_key(api_key)
    cache_entry.expires_at = _build_expiry()
    cache_entry.last_used_at = utc_now()
    return cache_entry


def get_cached_redcap_api_key(
    db: Session,
    *,
    user_session_id: UUID,
    redcap_host_id: UUID,
) -> str | None:
    cache_entry = db.scalar(
        select(REDCapApiKeyCache).where(
            REDCapApiKeyCache.user_session_id == user_session_id,
            REDCapApiKeyCache.redcap_host_id == redcap_host_id,
        )
    )
    if cache_entry is None:
        return None
    if cache_entry.expires_at <= utc_now():
        db.delete(cache_entry)
        return None

    try:
        decrypted_value = _get_fernet().decrypt(cache_entry.encrypted_api_key.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        db.delete(cache_entry)
        return None

    cache_entry.last_used_at = utc_now()
    cache_entry.expires_at = _build_expiry()
    return decrypted_value


def has_cached_redcap_api_key(
    db: Session,
    *,
    user_session_id: UUID,
    redcap_host_id: UUID | None,
) -> bool:
    if redcap_host_id is None:
        return False

    cache_entry = db.scalar(
        select(REDCapApiKeyCache).where(
            REDCapApiKeyCache.user_session_id == user_session_id,
            REDCapApiKeyCache.redcap_host_id == redcap_host_id,
        )
    )
    if cache_entry is None:
        return False
    if cache_entry.expires_at <= utc_now():
        return False
    try:
        _get_fernet().decrypt(cache_entry.encrypted_api_key.encode("utf-8"))
    except InvalidToken:
        return False
    return True


def clear_redcap_api_keys_for_session(db: Session, *, user_session_id: UUID) -> None:
    cache_entries = db.scalars(
        select(REDCapApiKeyCache).where(REDCapApiKeyCache.user_session_id == user_session_id)
    ).all()
    for cache_entry in cache_entries:
        db.delete(cache_entry)
