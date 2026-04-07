"""시간 단위 리소스 롤업 메트릭."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class ResourceHourlyRollup(Base, TimestampMixin):
    __tablename__ = "resource_hourly_rollups"
    __table_args__ = (
        UniqueConstraint(
            "bucket_start",
            "scope",
            "host",
            "environment",
            name="uq_resource_hourly_rollups_bucket_scope_host_env",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    bucket_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(30), nullable=False, index=True, default="LOCAL_RUNTIME")
    host: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    app_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_cpu_load_ratio_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_cpu_load_ratio_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_app_rss_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_app_rss_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_ollama_rss_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_ollama_rss_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_disk_used_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_disk_used_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    ollama_running_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
