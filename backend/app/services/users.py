from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, normalize_email, utc_now
from app.models.enums import Role
from app.models.session import UserSession
from app.models.user import User


class UserManagementError(ValueError):
    """Raised when a user-management action violates business rules."""


def list_users_for_actor(db: Session, actor: User) -> Sequence[User]:
    stmt = select(User)
    if actor.role == Role.ADMIN:
        stmt = stmt.where(User.role == Role.USER)

    role_rank = case(
        (User.role == Role.SUPER_ADMIN, 0),
        (User.role == Role.ADMIN, 1),
        else_=2,
    )

    return db.scalars(
        stmt.order_by(
            role_rank,
            User.is_active.desc(),
            func.lower(func.coalesce(User.full_name, User.email)),
        )
    ).all()


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.scalar(select(User).where(User.id == user_id))


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def allowed_creatable_roles(actor: User) -> tuple[Role, ...]:
    if actor.role == Role.SUPER_ADMIN:
        return (Role.ADMIN, Role.USER)
    if actor.role == Role.ADMIN:
        return (Role.USER,)
    return ()


def can_manage_target(actor: User, target_user: User) -> bool:
    if actor.role == Role.SUPER_ADMIN:
        return target_user.role != Role.SUPER_ADMIN and target_user.id != actor.id
    if actor.role == Role.ADMIN:
        return target_user.role == Role.USER
    return False


def _ensure_manageable_target(actor: User, target_user: User) -> None:
    if actor.role not in (Role.ADMIN, Role.SUPER_ADMIN):
        raise UserManagementError("You do not have permission to manage users.")

    if target_user.id == actor.id:
        raise UserManagementError("Your own account must be managed from a dedicated profile flow.")

    if actor.role == Role.ADMIN and target_user.role != Role.USER:
        raise UserManagementError("Admins can only manage standard users.")

    if target_user.role == Role.SUPER_ADMIN:
        raise UserManagementError("Super admin accounts are managed outside the web UI.")


def create_managed_user(
    db: Session,
    *,
    actor: User,
    email: str,
    password: str,
    full_name: str | None,
    role: Role,
) -> User:
    if role not in allowed_creatable_roles(actor):
        raise UserManagementError("You are not allowed to create that role.")

    normalized_email = normalize_email(email)
    if get_user_by_email(db, normalized_email) is not None:
        raise UserManagementError("A user with that email already exists.")

    cleaned_full_name = full_name.strip() if full_name and full_name.strip() else None
    user = User(
        email=normalized_email,
        full_name=cleaned_full_name,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def update_user_full_name(
    db: Session,
    *,
    actor: User,
    target_user: User,
    full_name: str | None,
) -> User:
    _ensure_manageable_target(actor, target_user)
    target_user.full_name = full_name.strip() if full_name and full_name.strip() else None
    return target_user


def update_user_email(
    db: Session,
    *,
    actor: User,
    target_user: User,
    email: str,
) -> User:
    _ensure_manageable_target(actor, target_user)
    normalized_email = normalize_email(email)
    existing_user = get_user_by_email(db, normalized_email)
    if existing_user is not None and existing_user.id != target_user.id:
        raise UserManagementError("A user with that email already exists.")

    target_user.email = normalized_email
    return target_user


def set_user_active_state(
    db: Session,
    *,
    actor: User,
    target_user: User,
    is_active: bool,
) -> User:
    _ensure_manageable_target(actor, target_user)
    target_user.is_active = is_active
    if not is_active:
        revoke_all_user_sessions(db, target_user)
    return target_user


def set_user_role(
    db: Session,
    *,
    actor: User,
    target_user: User,
    role: Role,
) -> User:
    _ensure_manageable_target(actor, target_user)
    if actor.role != Role.SUPER_ADMIN:
        raise UserManagementError("Only super admins can change roles.")
    if role == Role.SUPER_ADMIN:
        raise UserManagementError("Promoting to super admin is restricted to bootstrap scripts.")

    target_user.role = role
    return target_user


def reset_user_password(
    db: Session,
    *,
    actor: User,
    target_user: User,
    password: str,
) -> User:
    _ensure_manageable_target(actor, target_user)
    target_user.password_hash = hash_password(password)
    revoke_all_user_sessions(db, target_user)
    return target_user


def revoke_all_user_sessions(db: Session, user: User) -> None:
    sessions = db.scalars(select(UserSession).where(UserSession.user_id == user.id))
    for session in sessions:
        if session.revoked_at is None:
            session.revoked_at = utc_now()
