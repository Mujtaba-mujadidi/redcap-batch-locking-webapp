from datetime import timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.security import (
    create_session_token,
    ensure_utc_aware,
    hash_session_token,
    normalize_email,
    utc_now,
    verify_password,
)
from app.models.session import UserSession
from app.models.user import User


settings = get_settings()


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    normalized_email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.password_hash):
        return None

    user.last_login_at = utc_now()
    return user


def create_user_session(db: Session, *, user: User, request: Request) -> tuple[str, UserSession]:
    now = utc_now()
    raw_session_token = create_session_token()
    session = UserSession(
        user_id=user.id,
        session_token_hash=hash_session_token(raw_session_token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        last_seen_at=now,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    db.flush()
    return raw_session_token, session


def get_valid_session_by_token(db: Session, raw_session_token: str) -> UserSession | None:
    session = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(UserSession.session_token_hash == hash_session_token(raw_session_token))
    )
    if session is None:
        return None

    now = utc_now()
    if session.revoked_at is not None or ensure_utc_aware(session.expires_at) <= now:
        return None

    if session.user is None or not session.user.is_active:
        return None

    return session


def revoke_session(session: UserSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = utc_now()
