from sqlalchemy import Boolean, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class REDCapHost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "redcap_hosts"
    __table_args__ = (
        Index("ix_redcap_hosts_is_active", "is_active"),
    )

    base_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer)
    max_concurrent_jobs: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    jobs = relationship("Job", back_populates="redcap_host")
    mappings = relationship("InstrumentMapping", back_populates="redcap_host")
    api_key_cache_entries = relationship("REDCapApiKeyCache", back_populates="redcap_host", cascade="all, delete-orphan")
