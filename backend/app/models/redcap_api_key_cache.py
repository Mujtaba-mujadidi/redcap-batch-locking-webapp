from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class REDCapApiKeyCache(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "redcap_api_key_cache"
    __table_args__ = (
        UniqueConstraint("user_session_id", "redcap_host_id", name="uq_redcap_api_key_cache_session_host"),
        Index("ix_redcap_api_key_cache_expires_at", "expires_at"),
    )

    user_session_id: Mapped[UUID] = mapped_column(ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False)
    redcap_host_id: Mapped[UUID] = mapped_column(ForeignKey("redcap_hosts.id", ondelete="CASCADE"), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_fingerprint: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user_session = relationship("UserSession", back_populates="redcap_api_key_cache_entries")
    redcap_host = relationship("REDCapHost", back_populates="api_key_cache_entries")
