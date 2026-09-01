from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_session_token, ensure_utc_aware, hash_password, hash_session_token, utc_now
from app.models.enums import Role
from app.models.session import UserSession
from app.models.user import User

DESKTOP_USER_EMAIL = "desktop@local"
DESKTOP_USER_NAME = "Desktop User"


def is_desktop_mode() -> bool:
    return get_settings().is_desktop


def parse_expiry_date(raw_value: str | None) -> date | None:
    cleaned = (raw_value or "").strip()
    if not cleaned:
        return None
    return date.fromisoformat(cleaned)


def is_app_expired(*, today: date | None = None) -> bool:
    settings = get_settings()
    expiry_date = parse_expiry_date(settings.app_expiry_date)
    if expiry_date is None:
        return False
    return (today or date.today()) > expiry_date


def expiry_status(*, today: date | None = None) -> dict[str, object]:
    settings = get_settings()
    expiry_date = parse_expiry_date(settings.app_expiry_date)
    current_day = today or date.today()
    expired = expiry_date is not None and current_day > expiry_date
    days_remaining: int | None = None
    if expiry_date is not None:
        days_remaining = (expiry_date - current_day).days
    return {
        "expired": expired,
        "expiry_date": expiry_date.isoformat() if expiry_date else None,
        "days_remaining": days_remaining,
        "version": settings.app_version,
    }


def ensure_desktop_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == DESKTOP_USER_EMAIL))
    if user is not None:
        return user

    user = User(
        email=DESKTOP_USER_EMAIL,
        full_name=DESKTOP_USER_NAME,
        password_hash=hash_password("desktop-local-not-used"),
        role=Role.SUPER_ADMIN,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def ensure_desktop_session(db: Session) -> UserSession:
    user = ensure_desktop_user(db)
    session = db.scalar(
        select(UserSession)
        .where(UserSession.user_id == user.id)
        .where(UserSession.revoked_at.is_(None))
        .order_by(UserSession.created_at.desc())
    )
    if session is not None and ensure_utc_aware(session.expires_at) > utc_now():
        return session

    session = UserSession(
        user_id=user.id,
        session_token_hash=hash_session_token(create_session_token()),
        expires_at=utc_now() + timedelta(days=3650),
    )
    db.add(session)
    db.flush()
    return session


def get_desktop_session(db: Session) -> UserSession | None:
    if not is_desktop_mode():
        return None
    return ensure_desktop_session(db)
