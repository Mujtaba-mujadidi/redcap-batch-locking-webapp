from fastapi import APIRouter

from app.core.config import get_settings
from app.core.desktop import expiry_status, is_desktop_mode


router = APIRouter(prefix="/desktop", tags=["desktop"])


@router.get("/status")
def desktop_status() -> dict[str, object]:
    settings = get_settings()
    return {
        "mode": settings.app_mode,
        "desktop": is_desktop_mode(),
        **expiry_status(),
    }
