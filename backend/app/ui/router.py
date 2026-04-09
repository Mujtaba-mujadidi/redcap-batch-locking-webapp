from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utc_now
from app.db.session import get_db_session
from app.models.audit import AuditEvent
from app.models.enums import Role
from app.models.job import Job, Report
from app.models.mapping import InstrumentMapping
from app.models.session import UserSession
from app.models.user import User
from app.services.audit import record_audit_event
from app.services.auth import get_valid_session_by_token
from app.services.users import (
    UserManagementError,
    allowed_creatable_roles,
    can_manage_target,
    create_managed_user,
    get_user_by_id,
    list_users_for_actor,
    reset_user_password,
    set_user_active_state,
    set_user_role,
)


settings = get_settings()
router = APIRouter(include_in_schema=False)
app_dir = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(app_dir / "templates"))
templates.env.globals["asset_version"] = str(int((app_dir / "static" / "auth.css").stat().st_mtime))


def get_optional_session(request: Request, db: Session) -> tuple[str | None, UserSession | None]:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None, None

    session = get_valid_session_by_token(db, raw_token)
    return raw_token, session


def _can_manage_users(user: User) -> bool:
    return user.role in (Role.ADMIN, Role.SUPER_ADMIN)


def _build_sidebar_context(*, active_path: str, current_user: User | None = None) -> dict[str, object]:
    can_manage_users = current_user is not None and _can_manage_users(current_user)
    if current_user is None:
        nav_items = [
            {"label": "Sign In", "href": "/login", "is_active": active_path == "/login", "is_disabled": False},
            {"label": "Dashboard", "href": "/app", "is_active": False, "is_disabled": True},
            {"label": "Jobs", "href": "/jobs", "is_active": False, "is_disabled": True},
            {"label": "Mappings", "href": "/mappings", "is_active": False, "is_disabled": True},
            {"label": "Reports", "href": "/reports", "is_active": False, "is_disabled": True},
            {"label": "Users", "href": "/users", "is_active": False, "is_disabled": True},
        ]
    else:
        nav_items = [
            {"label": "Dashboard", "href": "/app", "is_active": active_path == "/app", "is_disabled": False},
            {"label": "Jobs", "href": "/jobs", "is_active": active_path == "/jobs", "is_disabled": False},
            {"label": "Mappings", "href": "/mappings", "is_active": active_path == "/mappings", "is_disabled": False},
            {"label": "Reports", "href": "/reports", "is_active": active_path == "/reports", "is_disabled": False},
            {
                "label": "Users",
                "href": "/users",
                "is_active": active_path == "/users",
                "is_disabled": not can_manage_users,
            },
        ]
    return {
        "nav_items": nav_items,
        "sidebar_user": current_user,
        "show_logout": current_user is not None,
    }


def _redirect_with_message(destination: str, *, success: str | None = None, error: str | None = None) -> RedirectResponse:
    params = {key: value for key, value in {"success": success, "error": error}.items() if value}
    url = destination if not params else f"{destination}?{urlencode(params)}"
    return RedirectResponse(url, status_code=303)


@router.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    destination = "/app" if session else "/login"
    return RedirectResponse(destination, status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session:
        return RedirectResponse("/app", status_code=303)

    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "page_title": "Sign In",
            "has_users": user_count > 0,
            "user_count": user_count,
            **_build_sidebar_context(active_path="/login"),
        },
    )


@router.get("/app", response_class=HTMLResponse)
def app_home(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    now = utc_now()
    dashboard_stats = {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "super_admins": db.scalar(
            select(func.count()).select_from(User).where(User.role == Role.SUPER_ADMIN)
        )
        or 0,
        "active_sessions": db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.revoked_at.is_(None), UserSession.expires_at > now)
        )
        or 0,
        "jobs": db.scalar(select(func.count()).select_from(Job)) or 0,
        "reports": db.scalar(select(func.count()).select_from(Report)) or 0,
        "mappings": db.scalar(select(func.count()).select_from(InstrumentMapping)) or 0,
        "audit_events": db.scalar(select(func.count()).select_from(AuditEvent)) or 0,
    }

    return templates.TemplateResponse(
        request=request,
        name="app_home.html",
        context={
            "page_title": "Workspace",
            "user": session.user,
            "session": session,
            "dashboard_stats": dashboard_stats,
            "can_manage_users": _can_manage_users(session.user),
            **_build_sidebar_context(active_path="/app", current_user=session.user),
        },
    )


def _render_workspace_placeholder(
    request: Request,
    *,
    current_user: User,
    page_title: str,
    section_label: str,
    heading: str,
    copy: str,
    active_path: str,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="placeholder_page.html",
        context={
            "page_title": page_title,
            "user": current_user,
            "section_label": section_label,
            "heading": heading,
            "copy": copy,
            **_build_sidebar_context(active_path=active_path, current_user=current_user),
        },
    )


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    return _render_workspace_placeholder(
        request,
        current_user=session.user,
        page_title="Jobs",
        section_label="Jobs",
        heading="Job workspace is the next build slice",
        copy="This section will handle CSV upload, REDCap preflight, job start, and execution monitoring.",
        active_path="/jobs",
    )


@router.get("/mappings", response_class=HTMLResponse)
def mappings_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    return _render_workspace_placeholder(
        request,
        current_user=session.user,
        page_title="Mappings",
        section_label="Mappings",
        heading="Mapping review is coming next",
        copy="This section will show REDCap metadata discovery, inferred form mappings, and confirmation workflows.",
        active_path="/mappings",
    )


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    return _render_workspace_placeholder(
        request,
        current_user=session.user,
        page_title="Reports",
        section_label="Reports",
        heading="Reports and exports will live here",
        copy="This area will list generated output files, downloadable job reports, and retention-aware report history.",
        active_path="/reports",
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db_session)):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    users = list_users_for_actor(db, current_user)
    user_rows = [
        {
            "user": user,
            "can_manage": can_manage_target(current_user, user),
            "can_change_role": current_user.role == Role.SUPER_ADMIN and can_manage_target(current_user, user),
        }
        for user in users
    ]

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "page_title": "Users",
            "user": current_user,
            "session": session,
            "Role": Role,
            "user_rows": user_rows,
            "allowed_roles": allowed_creatable_roles(current_user),
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
            "visible_admin_count": sum(1 for user in users if user.role == Role.ADMIN),
            "visible_user_count": sum(1 for user in users if user.role == Role.USER),
            "inactive_count": sum(1 for user in users if not user.is_active),
            **_build_sidebar_context(active_path="/users", current_user=current_user),
        },
    )


@router.post("/users/create")
def create_user_from_ui(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(default=""),
    password: str = Form(...),
    role: str = Form(default=Role.USER.value),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    if len(password) < 8:
        return _redirect_with_message("/users", error="Passwords must be at least 8 characters long.")

    try:
        created_user = create_managed_user(
            db,
            actor=current_user,
            email=email,
            password=password,
            full_name=full_name,
            role=Role(role),
        )
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            action="users.create",
            object_type="user",
            object_id=str(created_user.id),
            request=request,
            metadata={"email": created_user.email, "role": created_user.role.value},
        )
        db.commit()
    except UserManagementError as exc:
        db.rollback()
        return _redirect_with_message("/users", error=str(exc))
    except ValueError:
        db.rollback()
        return _redirect_with_message("/users", error="Invalid role selected.")

    return _redirect_with_message("/users", success=f"Created account for {created_user.email}.")


@router.post("/users/{user_id}/status")
def update_user_status_from_ui(
    user_id: UUID,
    request: Request,
    is_active: str = Form(...),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    target_user = get_user_by_id(db, user_id)
    if target_user is None:
        return _redirect_with_message("/users", error="User not found.")

    try:
        set_user_active_state(
            db,
            actor=current_user,
            target_user=target_user,
            is_active=is_active.lower() == "true",
        )
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            action="users.update_status",
            object_type="user",
            object_id=str(target_user.id),
            request=request,
            metadata={"is_active": target_user.is_active},
        )
        db.commit()
    except UserManagementError as exc:
        db.rollback()
        return _redirect_with_message("/users", error=str(exc))

    status_label = "activated" if target_user.is_active else "deactivated"
    return _redirect_with_message("/users", success=f"{target_user.email} {status_label}.")


@router.post("/users/{user_id}/role")
def update_user_role_from_ui(
    user_id: UUID,
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    target_user = get_user_by_id(db, user_id)
    if target_user is None:
        return _redirect_with_message("/users", error="User not found.")

    try:
        set_user_role(db, actor=current_user, target_user=target_user, role=Role(role))
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            action="users.update_role",
            object_type="user",
            object_id=str(target_user.id),
            request=request,
            metadata={"role": target_user.role.value},
        )
        db.commit()
    except UserManagementError as exc:
        db.rollback()
        return _redirect_with_message("/users", error=str(exc))
    except ValueError:
        db.rollback()
        return _redirect_with_message("/users", error="Invalid role selected.")

    return _redirect_with_message("/users", success=f"{target_user.email} is now {target_user.role.value}.")


@router.post("/users/{user_id}/password")
def reset_user_password_from_ui(
    user_id: UUID,
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db_session),
):
    _, session = get_optional_session(request, db)
    if session is None:
        return RedirectResponse("/login", status_code=303)

    current_user = session.user
    if not _can_manage_users(current_user):
        return RedirectResponse("/app", status_code=303)

    if len(password) < 8:
        return _redirect_with_message("/users", error="Passwords must be at least 8 characters long.")

    target_user = get_user_by_id(db, user_id)
    if target_user is None:
        return _redirect_with_message("/users", error="User not found.")

    try:
        reset_user_password(db, actor=current_user, target_user=target_user, password=password)
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            action="users.reset_password",
            object_type="user",
            object_id=str(target_user.id),
            request=request,
            metadata={"password_reset": True},
        )
        db.commit()
    except UserManagementError as exc:
        db.rollback()
        return _redirect_with_message("/users", error=str(exc))

    return _redirect_with_message("/users", success=f"Password reset for {target_user.email}.")
