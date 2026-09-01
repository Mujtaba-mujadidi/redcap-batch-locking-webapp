from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.desktop import expiry_status, is_app_expired, is_desktop_mode


class DesktopExpiryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not is_desktop_mode() or not is_app_expired():
            return await call_next(request)

        path = request.url.path
        if path in {"/health", "/api/v1/desktop/status"}:
            return await call_next(request)

        status = expiry_status()
        return JSONResponse(
            status_code=403,
            content={
                "detail": "This desktop app version has expired. Install the latest update to continue.",
                "desktop": status,
            },
        )
