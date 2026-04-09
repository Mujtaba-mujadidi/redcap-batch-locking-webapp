from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.ui.router import app_dir, router as ui_router


settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.mount("/static", StaticFiles(directory=str(app_dir / "static")), name="static")
app.include_router(ui_router)
app.include_router(api_router)

@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version}
