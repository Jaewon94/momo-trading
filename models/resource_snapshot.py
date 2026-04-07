"""시스템/프로세스 리소스 스냅샷."""
from uuid import uuid4

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class ResourceSnapshot(Base, TimestampMixin):
    __tablename__ = "resource_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    scope: Mapped[str] = mapped_column(String(30), nullable=False, index=True, default="LOCAL_RUNTIME")
    host: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    app_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    python_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    platform_system: Mapped[str | None] = mapped_column(String(40), nullable=True)
    platform_release: Mapped[str | None] = mapped_column(String(60), nullable=True)
    platform_machine: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cpu_count: Mapped[int | None] = mapped_column(nullable=True)
    app_pid: Mapped[int | None] = mapped_column(nullable=True)
    cpu_load_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_load_5m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_load_15m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_load_ratio_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_load_ratio_5m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_load_ratio_15m: Mapped[float | None] = mapped_column(Float, nullable=True)
    process_cpu_time_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_memory_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_used_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_available_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    swap_used_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_total_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_used_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_available_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_used_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    app_rss_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    ollama_rss_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    ollama_pid_count: Mapped[int | None] = mapped_column(nullable=True)
    ollama_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
