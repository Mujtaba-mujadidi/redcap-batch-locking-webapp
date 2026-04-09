from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_session
from app.core.config import get_settings
from app.core.security import utc_now
from app.db.session import get_db_session
from app.models.session import UserSession
from app.schemas.auth import AuthenticatedResponse, AuthSessionRead, AuthUserRead, LoginRequest, LogoutResponse
from app.services.audit import record_audit_event
from app.services.auth import authenticate_user, create_user_session, revoke_session


router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _build_auth_response(current_session: UserSession) -> AuthenticatedResponse:
    return AuthenticatedResponse(
        user=AuthUserRead.model_validate(current_session.user),
        session=AuthSessionRead.model_validate(current_session),
    )


def _set_session_cookie(response: Response, raw_token: str, expires_at: datetime) -> None:
    max_age = max(int((expires_at - utc_now()).total_seconds()), 0)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
        max_age=max_age,
        expires=expires_at,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
    )


@router.post("/login", response_model=AuthenticatedResponse)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthenticatedResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.is_two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Two-factor-enabled accounts are not supported by this login flow yet.",
        )

    raw_session_token, session = create_user_session(db, user=user, request=request)
    record_audit_event(
        db,
        actor_user_id=user.id,
        action="auth.login",
        object_type="user",
        object_id=str(user.id),
        request=request,
        metadata={"session_id": str(session.id)},
    )

    db.commit()
    db.refresh(session)
    db.refresh(user)

    _set_session_cookie(response, raw_session_token, session.expires_at)
    return _build_auth_response(session)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db_session),
    current_session: UserSession = Depends(get_current_session),
) -> LogoutResponse:
    revoke_session(current_session)
    record_audit_event(
        db,
        actor_user_id=current_session.user.id,
        action="auth.logout",
        object_type="user_session",
        object_id=str(current_session.id),
        request=request,
    )
    db.commit()
    _clear_session_cookie(response)
    return LogoutResponse(message="Logged out.")


@router.get("/me", response_model=AuthenticatedResponse)
def me(current_session: UserSession = Depends(get_current_session)) -> AuthenticatedResponse:
    return _build_auth_response(current_session)
