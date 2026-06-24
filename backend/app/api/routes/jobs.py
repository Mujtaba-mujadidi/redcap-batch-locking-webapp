from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.jobs import JobListItemRead, JobsListRead
from app.services.workspace_views import build_jobs_list


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobsListRead)
def list_jobs(
    limit: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> JobsListRead:
    payload = build_jobs_list(db, current_user=current_user, limit=limit)
    db.commit()
    return JobsListRead(
        items=[JobListItemRead(**item) for item in payload["items"]],
        has_active_jobs=bool(payload["has_active_jobs"]),
    )
