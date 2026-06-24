from pydantic import BaseModel

from app.schemas.auth import AuthUserRead


class WorkspacePermissionsRead(BaseModel):
    can_manage_users: bool
    can_manage_admins: bool


class WorkspaceStatsRead(BaseModel):
    users: int
    super_admins: int
    active_sessions: int
    jobs: int
    reports: int
    mappings: int
    audit_events: int


class WorkspaceSummaryRead(BaseModel):
    current_user: AuthUserRead
    permissions: WorkspacePermissionsRead
    stats: WorkspaceStatsRead
