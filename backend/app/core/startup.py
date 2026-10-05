from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.core.desktop import ensure_desktop_session, ensure_desktop_user, is_desktop_mode
from app.core.paths import ensure_app_data_dir, resolve_app_data_dir
from app.core.runtime_paths import alembic_ini_path, backend_root
from app.db.session import SessionLocal, reconfigure_engine
from app.services.job_lifecycle import recover_interrupted_active_jobs

logger = logging.getLogger(__name__)


def alembic_config_path():
    return alembic_ini_path()


def run_database_migrations() -> None:
    settings = get_settings()
    config = Config(str(alembic_ini_path()))
    config.set_main_option("script_location", str(backend_root() / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")


def prepare_desktop_runtime() -> None:
    if not is_desktop_mode():
        return

    settings = get_settings()
    app_data_dir = ensure_app_data_dir(resolve_app_data_dir(settings.app_data_dir))
    logger.info("Desktop app data directory: %s", app_data_dir)

    reconfigure_engine()
    run_database_migrations()

    with SessionLocal() as db:
        ensure_desktop_user(db)
        ensure_desktop_session(db)
        recovered = recover_interrupted_active_jobs(db)
        db.commit()
        if recovered:
            logger.warning("Recovered %s interrupted active job(s) so they can be resumed.", recovered)

    logger.info("Desktop runtime prepared.")
