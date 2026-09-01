from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.startup import prepare_desktop_runtime
from app.middleware.expiry import DesktopExpiryMiddleware
from app.ui.router import app_dir, router as ui_router


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    prepare_desktop_runtime()
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(app_dir / "static")), name="static")
app.include_router(ui_router)
app.include_router(api_router)

if settings.is_desktop:
    app.add_middleware(DesktopExpiryMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3847",
            "http://127.0.0.1:3847",
            "tauri://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health():
    payload: dict[str, object] = {
        "status": "ok",
        "version": settings.app_version,
        "mode": settings.app_mode,
    }
    if settings.is_desktop:
        payload["redcap_ssl_verify"] = settings.redcap_ssl_verify
    return payload
