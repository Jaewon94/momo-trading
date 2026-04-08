from __future__ import annotations

import json
import os
import platform
import re
import resource
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from core.config import settings
from core.database import AsyncSessionLocal, run_sqlite_write_with_retry
from models.execution_metric import ExecutionMetric
from models.resource_snapshot import ResourceSnapshot
from repositories.execution_metric_repository import ExecutionMetricRepository
from repositories.resource_snapshot_repository import ResourceSnapshotRepository

_VM_STAT_PAGE_SIZE_RE = re.compile(r"page size of (\d+) bytes")
_VM_STAT_VALUE_RE = re.compile(r"^Pages ([^:]+):\s+(\d+)\.$")
_SWAP_USED_RE = re.compile(r"used = ([0-9.]+)([MG])")


class LocalResourceCollector:
    def collect_snapshot(self) -> dict[str, Any]:
        host = socket.gethostname()
        load1, load5, load15 = self._safe_loadavg()
        cpu_count = max(os.cpu_count() or 1, 1)
        memory = self._memory_snapshot()
        process_cpu_time = resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime
        disk = shutil.disk_usage(Path.cwd())
        app_rss_bytes = self._current_process_rss_bytes()
        ollama_running, ollama_rss_mb, ollama_pid_count = self._ollama_status()

        return {
            "scope": "LOCAL_RUNTIME",
            "host": host,
            "app_name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "python_version": platform.python_version(),
            "platform_system": platform.system(),
            "platform_release": platform.release(),
            "platform_machine": platform.machine(),
            "cpu_count": cpu_count,
            "app_pid": os.getpid(),
            "cpu_load_1m": round(load1, 3) if load1 is not None else None,
            "cpu_load_5m": round(load5, 3) if load5 is not None else None,
            "cpu_load_15m": round(load15, 3) if load15 is not None else None,
            "cpu_load_ratio_1m": round(load1 / cpu_count, 3) if load1 is not None else None,
            "cpu_load_ratio_5m": round(load5 / cpu_count, 3) if load5 is not None else None,
            "cpu_load_ratio_15m": round(load15 / cpu_count, 3) if load15 is not None else None,
            "process_cpu_time_sec": round(process_cpu_time, 3),
            "total_memory_mb": memory.get("total_memory_mb"),
            "memory_used_mb": memory.get("memory_used_mb"),
            "memory_available_mb": memory.get("memory_available_mb"),
            "memory_percent": memory.get("memory_percent"),
            "swap_used_mb": memory.get("swap_used_mb"),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2) if disk.total else None,
            "disk_used_gb": round(disk.used / (1024 ** 3), 2) if disk.total else None,
            "disk_available_gb": round(disk.free / (1024 ** 3), 2) if disk.total else None,
            "disk_used_percent": round((disk.used / disk.total) * 100.0, 2) if disk.total else None,
            "app_rss_mb": round(app_rss_bytes / (1024 * 1024), 2) if app_rss_bytes is not None else None,
            "ollama_rss_mb": ollama_rss_mb,
            "ollama_pid_count": ollama_pid_count,
            "ollama_running": ollama_running,
            "detail": {
                "collector": "LocalResourceCollector",
                "python_executable": sys.executable,
                "cwd": str(Path.cwd()),
            },
        }

    @staticmethod
    def _safe_loadavg() -> tuple[float | None, float | None, float | None]:
        try:
            return tuple(float(item) for item in os.getloadavg())  # type: ignore[return-value]
        except OSError:
            return (None, None, None)

    def _memory_snapshot(self) -> dict[str, float | None]:
        total_bytes = self._read_total_memory_bytes()
        available_bytes = self._read_available_memory_bytes()
        swap_used_mb = self._read_swap_used_mb()
        if total_bytes is None:
            return {
                "total_memory_mb": None,
                "memory_used_mb": None,
                "memory_available_mb": None,
                "memory_percent": None,
                "swap_used_mb": swap_used_mb,
            }
        if available_bytes is None:
            return {
                "total_memory_mb": round(total_bytes / (1024 * 1024), 2),
                "memory_used_mb": None,
                "memory_available_mb": None,
                "memory_percent": None,
                "swap_used_mb": swap_used_mb,
            }
        used_bytes = max(total_bytes - available_bytes, 0)
        return {
            "total_memory_mb": round(total_bytes / (1024 * 1024), 2),
            "memory_used_mb": round(used_bytes / (1024 * 1024), 2),
            "memory_available_mb": round(available_bytes / (1024 * 1024), 2),
            "memory_percent": round((used_bytes / total_bytes) * 100.0, 2) if total_bytes else None,
            "swap_used_mb": swap_used_mb,
        }

    @staticmethod
    def _run_command(args: list[str]) -> str:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"command failed: {' '.join(args)}")
        return completed.stdout

    def _read_total_memory_bytes(self) -> int | None:
        try:
            return int(self._run_command(["sysctl", "-n", "hw.memsize"]).strip())
        except Exception:
            return None

    def _read_available_memory_bytes(self) -> int | None:
        try:
            output = self._run_command(["vm_stat"])
        except Exception:
            return None

        page_size_match = _VM_STAT_PAGE_SIZE_RE.search(output)
        if not page_size_match:
            return None
        page_size = int(page_size_match.group(1))

        values: dict[str, int] = {}
        for raw_line in output.splitlines():
            match = _VM_STAT_VALUE_RE.match(raw_line.strip())
            if not match:
                continue
            values[match.group(1)] = int(match.group(2))

        available_pages = (
            values.get("free", 0)
            + values.get("inactive", 0)
            + values.get("speculative", 0)
        )
        return available_pages * page_size

    def _read_swap_used_mb(self) -> float | None:
        try:
            output = self._run_command(["sysctl", "vm.swapusage"])
        except Exception:
            return None
        match = _SWAP_USED_RE.search(output)
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2)
        if unit == "G":
            value *= 1024.0
        return round(value, 2)

    @staticmethod
    def _current_process_rss_bytes() -> int | None:
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss = int(usage.ru_maxrss)
            if rss <= 0:
                return None
            # macOS reports bytes, Linux typically reports KiB.
            return rss if rss >= (1024 * 1024) else rss * 1024
        except Exception:
            return None

    def _ollama_status(self) -> tuple[bool, float | None, int]:
        try:
            output = self._run_command(["pgrep", "-x", "ollama"])
        except Exception:
            return (False, None, 0)

        pids = [line.strip() for line in output.splitlines() if line.strip()]
        if not pids:
            return (False, None, 0)

        total_rss_kb = 0
        found_rss = False
        for pid in pids:
            try:
                rss_output = self._run_command(["ps", "-o", "rss=", "-p", pid]).strip()
                total_rss_kb += int(rss_output or "0")
                found_rss = True
            except Exception:
                continue

        rss_mb = round(total_rss_kb / 1024.0, 2) if found_rss else None
        return (True, rss_mb, len(pids))


class ObservabilityService:
    def __init__(self, collector: LocalResourceCollector | None = None) -> None:
        self._collector = collector or LocalResourceCollector()

    async def record_execution_metric(
        self,
        *,
        metric_type: str,
        metric_name: str,
        status: str,
        cycle_id: str | None = None,
        symbol: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        elapsed_ms: int | None = None,
        item_count: int | None = None,
        success_count: int | None = None,
        error_count: int | None = None,
        retry_count: int | None = None,
        fallback_used: bool = False,
        detail: dict[str, Any] | None = None,
    ) -> ExecutionMetric | None:
        entry = ExecutionMetric(
            metric_type=metric_type,
            metric_name=metric_name,
            status=status,
            cycle_id=cycle_id,
            symbol=symbol,
            provider=provider,
            model=model,
            elapsed_ms=elapsed_ms,
            item_count=item_count,
            success_count=success_count,
            error_count=error_count,
            retry_count=retry_count,
            fallback_used=fallback_used,
            detail=self._serialize_detail(detail),
        )
        try:
            async def _persist() -> None:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        await ExecutionMetricRepository(session).create(entry)

            await run_sqlite_write_with_retry(_persist)
            return entry
        except Exception as exc:
            logger.debug("실행 메트릭 저장 실패: {}", str(exc))
            return None

    async def record_llm_call(
        self,
        *,
        status: str,
        provider: str | None,
        model: str | None,
        tier: str,
        elapsed_ms: int | None,
        prompt_chars: int,
        response_chars: int | None = None,
        retry_count: int = 0,
        fallback_used: bool = False,
        cycle_id: str | None = None,
        symbol: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> ExecutionMetric | None:
        merged_detail = {
            "tier": tier,
            "prompt_chars": prompt_chars,
            "response_chars": response_chars,
        }
        if detail:
            merged_detail.update(detail)
        return await self.record_execution_metric(
            metric_type="LLM_CALL",
            metric_name="LLM_GENERATE",
            status=status,
            cycle_id=cycle_id,
            symbol=symbol,
            provider=provider,
            model=model,
            elapsed_ms=elapsed_ms,
            retry_count=retry_count,
            fallback_used=fallback_used,
            detail=merged_detail,
        )

    async def record_news_poll(
        self,
        *,
        status: str,
        elapsed_ms: int,
        item_count: int,
        success_count: int,
        error_count: int,
        detail: dict[str, Any] | None = None,
    ) -> ExecutionMetric | None:
        return await self.record_execution_metric(
            metric_type="JOB",
            metric_name="NEWS_POLL",
            status=status,
            elapsed_ms=elapsed_ms,
            item_count=item_count,
            success_count=success_count,
            error_count=error_count,
            detail=detail,
        )

    async def record_resource_snapshot(
        self,
        snapshot: dict[str, Any] | None = None,
    ) -> ResourceSnapshot | None:
        payload = snapshot or self._collector.collect_snapshot()
        detail = payload.get("detail")
        entry = ResourceSnapshot(
            scope=str(payload.get("scope") or "LOCAL_RUNTIME"),
            host=str(payload.get("host") or socket.gethostname()),
            app_name=str(payload.get("app_name") or settings.APP_NAME),
            environment=str(payload.get("environment") or settings.ENVIRONMENT),
            python_version=str(payload.get("python_version") or "") or None,
            platform_system=str(payload.get("platform_system") or "") or None,
            platform_release=str(payload.get("platform_release") or "") or None,
            platform_machine=str(payload.get("platform_machine") or "") or None,
            cpu_count=self._optional_int(payload.get("cpu_count")),
            app_pid=self._optional_int(payload.get("app_pid")),
            cpu_load_1m=self._optional_float(payload.get("cpu_load_1m")),
            cpu_load_5m=self._optional_float(payload.get("cpu_load_5m")),
            cpu_load_15m=self._optional_float(payload.get("cpu_load_15m")),
            cpu_load_ratio_1m=self._optional_float(payload.get("cpu_load_ratio_1m")),
            cpu_load_ratio_5m=self._optional_float(payload.get("cpu_load_ratio_5m")),
            cpu_load_ratio_15m=self._optional_float(payload.get("cpu_load_ratio_15m")),
            process_cpu_time_sec=self._optional_float(payload.get("process_cpu_time_sec")),
            total_memory_mb=self._optional_float(payload.get("total_memory_mb")),
            memory_used_mb=self._optional_float(payload.get("memory_used_mb")),
            memory_available_mb=self._optional_float(payload.get("memory_available_mb")),
            memory_percent=self._optional_float(payload.get("memory_percent")),
            swap_used_mb=self._optional_float(payload.get("swap_used_mb")),
            disk_total_gb=self._optional_float(payload.get("disk_total_gb")),
            disk_used_gb=self._optional_float(payload.get("disk_used_gb")),
            disk_available_gb=self._optional_float(payload.get("disk_available_gb")),
            disk_used_percent=self._optional_float(payload.get("disk_used_percent")),
            app_rss_mb=self._optional_float(payload.get("app_rss_mb")),
            ollama_rss_mb=self._optional_float(payload.get("ollama_rss_mb")),
            ollama_pid_count=self._optional_int(payload.get("ollama_pid_count")),
            ollama_running=bool(payload.get("ollama_running")),
            detail=self._serialize_detail(detail),
        )
        try:
            async def _persist() -> None:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        await ResourceSnapshotRepository(session).create(entry)

            await run_sqlite_write_with_retry(_persist)
            return entry
        except Exception as exc:
            logger.debug("리소스 스냅샷 저장 실패: {}", str(exc))
            return None

    @staticmethod
    def _serialize_detail(detail: dict[str, Any] | None) -> str | None:
        if not detail:
            return None
        return json.dumps(detail, ensure_ascii=False, default=str)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


observability_service = ObservabilityService()
