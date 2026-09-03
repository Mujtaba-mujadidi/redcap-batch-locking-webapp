from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.desktop import router as desktop_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.mappings import router as mappings_router
from app.api.routes.reports import router as reports_router
from app.api.routes.workspace import router as workspace_router


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(desktop_router)
api_router.include_router(workspace_router)
api_router.include_router(jobs_router)
api_router.include_router(mappings_router)
api_router.include_router(reports_router)
