"""시간 단위 실행 메트릭 롤업."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class ExecutionMetricHourlyRollup(Base, TimestampMixin):
    __tablename__ = "execution_metric_hourly_rollups"
    __table_args__ = (
        UniqueConstraint(
            "bucket_start",
            "metric_type",
            "metric_name",
            "provider",
            "model",
            name="uq_execution_metric_hourly_rollups_bucket_dimensions",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    bucket_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    item_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
