from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.mappings import MappingReviewItemRead, MappingReviewRead
from app.services.workspace_views import build_mapping_review


router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.get("/current", response_model=MappingReviewRead)
def current_mapping_review(
    job_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MappingReviewRead:
    payload = build_mapping_review(db, current_user=current_user, job_id=job_id)
    return MappingReviewRead(
        job_id=payload["job_id"],
        project_id=payload["project_id"],
        project_title=payload["project_title"],
        host_label=payload["host_label"],
        refresh_decision_pending=bool(payload["refresh_decision_pending"]),
        confirmed_mapping_count=int(payload["confirmed_mapping_count"]),
        rows=[MappingReviewItemRead(**item) for item in payload["rows"]],
    )
