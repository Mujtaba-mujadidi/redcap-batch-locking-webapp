from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MappingConfidence, MappingStatus
from app.models.types import enum_type


class InstrumentMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "instrument_mappings"
    __table_args__ = (
        UniqueConstraint(
            "redcap_host_id",
            "redcap_project_id",
            "instrument_name",
            name="uq_instrument_mappings_host_project_instrument",
        ),
        Index("ix_instrument_mappings_status", "status"),
    )

    redcap_host_id: Mapped[UUID | None] = mapped_column(ForeignKey("redcap_hosts.id", ondelete="SET NULL"))
    redcap_project_id: Mapped[str] = mapped_column(String(100), nullable=False)
    instrument_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[MappingStatus] = mapped_column(enum_type(MappingStatus, "mapping_status"), nullable=False)
    confidence: Mapped[MappingConfidence] = mapped_column(
        enum_type(MappingConfidence, "mapping_confidence"),
        nullable=False,
    )
    form_complete_field_name: Mapped[str | None] = mapped_column(String(255))
    crf_status_field_name: Mapped[str | None] = mapped_column(String(255))
    lock_date_field_name: Mapped[str | None] = mapped_column(String(255))
    coded_values_json: Mapped[dict | None] = mapped_column(JSON)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drift_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    redcap_host = relationship("REDCapHost", back_populates="mappings")
    confirmed_by_user = relationship("User", back_populates="confirmed_mappings")
