from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.desktop import get_desktop_session
from app.db.session import get_db_session
from app.models.enums import Role
from app.models.session import UserSession
from app.models.user import User


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
    )


def get_current_session(db: Session = Depends(get_db_session)) -> UserSession:
    desktop_session = get_desktop_session(db)
    if desktop_session is not None:
        return desktop_session
    raise _credentials_exception()


def get_current_user(current_session: UserSession = Depends(get_current_session)) -> User:
    return current_session.user


def require_roles(*roles: Role) -> Callable[[User], User]:
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return dependency
