"""fingerprint 기준으로 묶인 운영 에러 incident."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class ErrorIncident(Base, TimestampMixin):
    __tablename__ = "error_incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    component: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="ERROR")
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="OPEN")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    exception_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    owner_note: Mapped[str | None] = mapped_column(Text, nullable=True)
