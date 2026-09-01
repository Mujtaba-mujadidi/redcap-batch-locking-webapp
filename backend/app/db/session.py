from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite:") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def reconfigure_engine() -> None:
    global engine, SessionLocal
    refreshed_settings = get_settings()
    engine = create_engine(
        refreshed_settings.database_url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if refreshed_settings.database_url.startswith("sqlite:") else {},
    )
    SessionLocal.configure(bind=engine)


def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
