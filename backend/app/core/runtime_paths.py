from __future__ import annotations

import sys
from pathlib import Path


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def backend_root() -> Path:
    if is_frozen_runtime():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[2]


def alembic_ini_path() -> Path:
    return backend_root() / "alembic.ini"


def alembic_versions_dir() -> Path:
    return backend_root() / "alembic" / "versions"
