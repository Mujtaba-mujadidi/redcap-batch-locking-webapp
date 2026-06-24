from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.reports import ReportListItemRead, ReportsListRead
from app.services.workspace_views import build_reports_list


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=ReportsListRead)
def list_reports(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ReportsListRead:
    items = build_reports_list(db, current_user=current_user)
    db.commit()
    return ReportsListRead(items=[ReportListItemRead(**item) for item in items])
