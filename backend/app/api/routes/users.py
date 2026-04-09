from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db_session
from app.models.enums import Role
from app.models.user import User
from app.schemas.user import UserCreateRequest, UserRead, UserUpdateRequest
from app.services.audit import record_audit_event
from app.services.users import (
    UserManagementError,
    create_managed_user,
    get_user_by_id,
    list_users_for_actor,
    reset_user_password,
    set_user_active_state,
    set_user_role,
    update_user_email,
    update_user_full_name,
)


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles(Role.ADMIN, Role.SUPER_ADMIN)),
) -> list[UserRead]:
    return [UserRead.model_validate(user) for user in list_users_for_actor(db, current_user)]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles(Role.ADMIN, Role.SUPER_ADMIN)),
) -> UserRead:
    try:
        user = create_managed_user(
            db,
            actor=current_user,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
        )
    except UserManagementError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event(
        db,
        actor_user_id=current_user.id,
        action="users.create",
        object_type="user",
        object_id=str(user.id),
        request=request,
        metadata={"email": user.email, "role": user.role.value},
    )
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles(Role.ADMIN, Role.SUPER_ADMIN)),
) -> UserRead:
    target_user = get_user_by_id(db, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    fields_set = payload.model_fields_set
    if not fields_set:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided.")

    changes: dict[str, object] = {}
    try:
        if payload.email is not None:
            update_user_email(db, actor=current_user, target_user=target_user, email=payload.email)
            changes["email"] = target_user.email

        if "full_name" in fields_set:
            update_user_full_name(db, actor=current_user, target_user=target_user, full_name=payload.full_name)
            changes["full_name"] = target_user.full_name

        if payload.is_active is not None:
            set_user_active_state(db, actor=current_user, target_user=target_user, is_active=payload.is_active)
            changes["is_active"] = target_user.is_active

        if payload.role is not None:
            set_user_role(db, actor=current_user, target_user=target_user, role=payload.role)
            changes["role"] = target_user.role.value

        if payload.password is not None:
            reset_user_password(db, actor=current_user, target_user=target_user, password=payload.password)
            changes["password_reset"] = True
    except UserManagementError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid changes provided.")

    record_audit_event(
        db,
        actor_user_id=current_user.id,
        action="users.update",
        object_type="user",
        object_id=str(target_user.id),
        request=request,
        metadata=changes,
    )
    db.commit()
    db.refresh(target_user)
    return UserRead.model_validate(target_user)
