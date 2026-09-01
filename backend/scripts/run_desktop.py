#!/usr/bin/env python3
"""Launch the desktop API profile on localhost."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path


def _ensure_backend_import_path() -> None:
    if getattr(sys, "frozen", False):
        backend_root = Path(getattr(sys, "_MEIPASS"))
    else:
        backend_root = Path(__file__).resolve().parents[1]
    backend_root_str = str(backend_root)
    if backend_root_str not in sys.path:
        sys.path.insert(0, backend_root_str)


def _default_expiry_date() -> str:
    return (date.today() + timedelta(days=180)).isoformat()


def configure_desktop_environment() -> None:
    os.environ["APP_MODE"] = "desktop"
    os.environ.setdefault("APP_EXPIRY_DATE", _default_expiry_date())
    os.environ.setdefault("DESKTOP_API_HOST", "127.0.0.1")
    os.environ.setdefault("DESKTOP_API_PORT", "8765")
    os.environ.setdefault(
        "REDCAP_API_KEY_CACHE_SECRET",
        "desktop-local-redcap-api-key-cache-secret",
    )
    # Oxford REDCap uses an internal CA that bundled Python cannot verify.
    os.environ["REDCAP_SSL_VERIFY"] = "false"


def main() -> None:
    _ensure_backend_import_path()
    configure_desktop_environment()

    import uvicorn

    from app.core.config import get_settings
    from app.core.startup import prepare_desktop_runtime

    settings = get_settings()
    prepare_desktop_runtime()
    uvicorn.run(
        "app.main:app",
        host=settings.desktop_api_host,
        port=settings.desktop_api_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
