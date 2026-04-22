"""운영 중 발생한 원시 에러 이벤트."""
from uuid import uuid4

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class ErrorEvent(Base, TimestampMixin):
    __tablename__ = "error_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="ERROR")
    component: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    handled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exception_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stacktrace: Mapped[str | None] = mapped_column(Text, nullable=True)
    cycle_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    count_hint: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
