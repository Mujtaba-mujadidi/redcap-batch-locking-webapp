from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.auth import AuthUserRead
from app.schemas.workspace import WorkspacePermissionsRead, WorkspaceStatsRead, WorkspaceSummaryRead
from app.services.workspace_views import build_dashboard_summary


router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/summary", response_model=WorkspaceSummaryRead)
def workspace_summary(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceSummaryRead:
    summary = build_dashboard_summary(db, current_user=current_user)
    return WorkspaceSummaryRead(
        current_user=AuthUserRead.model_validate(summary["current_user"]),
        permissions=WorkspacePermissionsRead(**summary["permissions"]),
        stats=WorkspaceStatsRead(**summary["stats"]),
    )
