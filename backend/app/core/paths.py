from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_app_data_dir(explicit_dir: str | None = None) -> Path:
    if explicit_dir:
        return Path(explicit_dir).expanduser().resolve()

    env_dir = os.getenv("APP_DATA_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    app_name = "REDCap Batch Locking"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    if os.name == "nt":
        appdata = os.getenv("APPDATA", "").strip()
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / app_name
    return Path.home() / ".local" / "share" / app_name


def ensure_app_data_dir(app_data_dir: Path) -> Path:
    app_data_dir.mkdir(parents=True, exist_ok=True)
    return app_data_dir


def sqlite_database_path(app_data_dir: Path) -> Path:
    return app_data_dir / "app.db"
