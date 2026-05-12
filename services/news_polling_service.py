"""자동 뉴스 폴링 + 신규 뉴스 이벤트 발행."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.config import settings
from core.events import Event, EventType, event_bus
from services.activity_logger import activity_logger
from services.bloomberg_news_service import bloomberg_news_service
from services.cnbc_news_service import cnbc_news_service
from services.investing_news_service import investing_news_service
from services.nasdaq_news_service import nasdaq_news_service
from services.news_ingest_service import news_ingest_service
from services.error_capture_service import error_capture_service
from services.krx_kind_disclosure_service import krx_kind_disclosure_service
from services.news_translation_service import news_translation_service
from services.open_dart_disclosure_service import open_dart_disclosure_service
from services.news_runtime_service import news_runtime_service
from services.seeking_alpha_news_service import seeking_alpha_news_service
from services.yonhap_news_service import yonhap_news_service
from trading.enums import ActivityPhase, ActivityType


@dataclass(frozen=True)
class NewsSourcePollSpec:
    source_code: str
    enabled: bool
    skip_message: str
    fetch: Callable[[], Awaitable[list[dict[str, Any]]]]


@dataclass(frozen=True)
class NewsSourcePollResult:
    source_code: str
    status: str
    message: str
    counts: dict[str, int] | None
    items: list[dict[str, Any]]


class NewsPollingService:
    async def poll_sources(self, session, *, market_hours: bool, mode: str | None = None) -> dict:
        started_at = time.time()
        runtime_mode = mode or ("AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS")
        source_specs = self._build_source_specs(session, page_count=max(int(settings.NEWS_POLL_PAGE_COUNT or 25), 1))
        if not settings.NEWS_POLL_ENABLED:
            summary = {"skipped": True, "reason": "NEWS_POLL_ENABLED disabled"}
            for spec in source_specs:
                news_runtime_service.record_source_result(
                    spec.source_code,
                    status="SKIPPED",
                    mode=runtime_mode,
                    message=summary["reason"],
                    counts=summary,
                    update_overall=False,
                )
            news_runtime_service.record_overall_result(
                status="SKIPPED",
                mode=runtime_mode,
                message=summary["reason"],
            )
            summary["activity_log"] = {
                "summary": "🛰 뉴스 자동 수집 스킵 · NEWS_POLL_ENABLED 비활성",
                "detail": {"mode": runtime_mode, "reason": summary["reason"]},
            }
            summary["metric_payload"] = self._build_metric_payload(
                status="SKIPPED",
                elapsed_ms=int((time.time() - started_at) * 1000),
                item_count=0,
                success_count=0,
                error_count=0,
                detail={"mode": runtime_mode, "market_hours": market_hours, "reason": summary["reason"]},
            )
            return summary
        source_results = await self._poll_enabled_sources(source_specs)
        all_items: list[dict[str, Any]] = []
        for spec in source_specs:
            result = source_results[spec.source_code]
            all_items.extend(result.items)

        prepared_items = await news_translation_service.translate_items(all_items) if all_items else []
        detailed = await news_ingest_service.ingest_items_detailed(session, prepared_items)
        summary = dict(detailed["summary"])
        source_summaries = {
            str(source_code or "").upper(): dict(counts or {})
            for source_code, counts in (detailed.get("source_summaries") or {}).items()
        }
        published_events = 0

        for item in detailed["created_items"]:
            symbols = list(item.get("symbols") or [])
            if not symbols:
                continue
            await event_bus.publish(Event(
                type=EventType.NEW_NEWS_ITEM,
                data={
                    "symbols": symbols,
                    "title": item.get("title"),
                    "source_code": item.get("source_code"),
                    "published_at": item.get("published_at"),
                },
                source="news_polling_service",
            ))
            published_events += 1

        source_briefs = []
        for spec in source_specs:
            result = source_results[spec.source_code]
            counts = dict(result.counts or {})
            if result.status not in {"ERROR", "SKIPPED"}:
                counts = self._merge_runtime_counts(counts, source_summaries.get(spec.source_code))
            runtime_status = self._resolve_runtime_status(result, counts)
            runtime_message = self._build_source_runtime_message(result, counts)
            news_runtime_service.record_source_result(
                spec.source_code,
                status=runtime_status,
                mode=runtime_mode,
                message=runtime_message,
                counts=counts,
                update_overall=False,
            )
            source_briefs.append({
                "source_code": spec.source_code,
                "status": runtime_status,
                "received": int(counts.get("received") or 0),
                "created": int(counts.get("created") or 0),
                "duplicates": int(counts.get("duplicates") or 0),
                "skipped": int(counts.get("skipped") or 0),
                "message": runtime_message,
            })

        activity_log = {
            "summary": (
                "🛰 뉴스 자동 수집 완료 · "
                f"신규 {int(summary.get('created') or 0)}건 · "
                f"중복 {int(summary.get('duplicates') or 0)}건 · "
                f"스킵 {int(summary.get('skipped') or 0)}건"
            ),
            "detail": {
                "mode": runtime_mode,
                "market_hours": market_hours,
                "summary": summary,
                "published_events": published_events,
                "sources": source_briefs,
            },
        }
        source_error_count = sum(1 for result in source_results.values() if result.status == "ERROR")
        news_runtime_service.record_overall_result(
            status=self._resolve_overall_status(summary, source_error_count=source_error_count),
            mode=runtime_mode,
            message=self._build_overall_runtime_message(summary, source_error_count=source_error_count),
        )
        metric_payload = self._build_metric_payload(
            status="PARTIAL_ERROR" if source_error_count else "SUCCESS",
            elapsed_ms=int((time.time() - started_at) * 1000),
            item_count=int(summary.get("received") or 0),
            success_count=int(summary.get("created") or 0),
            error_count=source_error_count,
            detail={
                "mode": runtime_mode,
                "market_hours": market_hours,
                "duplicates": int(summary.get("duplicates") or 0),
                "skipped": int(summary.get("skipped") or 0),
                "published_events": published_events,
                "sources": source_briefs,
            },
        )

        return {
            **summary,
            "published_events": published_events,
            "market_hours": market_hours,
            "metric_payload": metric_payload,
            "activity_log": activity_log,
        }

    async def log_activity_from_summary(self, poll_summary: dict[str, Any]) -> None:
        activity_log = poll_summary.get("activity_log")
        if not isinstance(activity_log, dict):
            return
        summary = str(activity_log.get("summary") or "").strip()
        if not summary:
            return
        detail = activity_log.get("detail")
        await self._log_news_activity(
            summary,
            detail=detail if isinstance(detail, dict) else None,
        )

    async def _log_news_activity(self, summary: str, *, detail: dict[str, Any] | None = None) -> None:
        try:
            await activity_logger.log(
                ActivityType.SCHEDULE,
                ActivityPhase.PROGRESS,
                summary,
                detail=detail,
            )
        except Exception:
            # 뉴스 수집 자체를 로그 실패로 막지 않는다.
            return

    @staticmethod
    def _build_metric_payload(
        *,
        status: str,
        elapsed_ms: int,
        item_count: int,
        success_count: int,
        error_count: int,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "elapsed_ms": elapsed_ms,
            "item_count": item_count,
            "success_count": success_count,
            "error_count": error_count,
            "detail": detail,
        }

    def _build_source_specs(self, session, *, page_count: int) -> list[NewsSourcePollSpec]:
        return [
            NewsSourcePollSpec(
                source_code="DART",
                enabled=bool(settings.OPEN_DART_API_KEY),
                skip_message="OPEN_DART_API_KEY missing",
                fetch=lambda: open_dart_disclosure_service.fetch_recent_disclosures(
                    days=1,
                    page_count=page_count,
                ),
            ),
            NewsSourcePollSpec(
                source_code="KRX",
                enabled=True,
                skip_message="",
                fetch=lambda: krx_kind_disclosure_service.fetch_recent_disclosures(page_count=page_count),
            ),
            NewsSourcePollSpec(
                source_code="YONHAP",
                enabled=bool(settings.NEWS_DOMESTIC_MEDIA_ENABLED),
                skip_message="NEWS_DOMESTIC_MEDIA_ENABLED disabled",
                fetch=lambda: yonhap_news_service.fetch_recent_news(session, limit=page_count),
            ),
            NewsSourcePollSpec(
                source_code="BLOOMBERG",
                enabled=bool(settings.NEWS_INCLUDE_FOREIGN),
                skip_message="NEWS_INCLUDE_FOREIGN disabled",
                fetch=lambda: bloomberg_news_service.fetch_recent_news(limit=page_count),
            ),
            NewsSourcePollSpec(
                source_code="CNBC",
                enabled=bool(settings.NEWS_INCLUDE_FOREIGN),
                skip_message="NEWS_INCLUDE_FOREIGN disabled",
                fetch=lambda: cnbc_news_service.fetch_recent_news(limit=page_count),
            ),
            NewsSourcePollSpec(
                source_code="NASDAQ",
                enabled=bool(settings.NEWS_INCLUDE_FOREIGN and settings.NEWS_NASDAQ_ENABLED),
                skip_message=(
                    "NEWS_NASDAQ_ENABLED disabled"
                    if settings.NEWS_INCLUDE_FOREIGN
                    else "NEWS_INCLUDE_FOREIGN disabled"
                ),
                fetch=lambda: nasdaq_news_service.fetch_recent_news(limit=page_count),
            ),
            NewsSourcePollSpec(
                source_code="INVESTING",
                enabled=bool(settings.NEWS_INCLUDE_FOREIGN),
                skip_message="NEWS_INCLUDE_FOREIGN disabled",
                fetch=lambda: investing_news_service.fetch_recent_news(limit=page_count),
            ),
            NewsSourcePollSpec(
                source_code="SEEKING_ALPHA",
                enabled=bool(settings.NEWS_INCLUDE_FOREIGN),
                skip_message="NEWS_INCLUDE_FOREIGN disabled",
                fetch=lambda: seeking_alpha_news_service.fetch_recent_news(limit=page_count),
            ),
        ]

    async def _poll_enabled_sources(
        self,
        source_specs: list[NewsSourcePollSpec],
    ) -> dict[str, NewsSourcePollResult]:
        semaphore = asyncio.Semaphore(max(int(settings.NEWS_FETCH_CONCURRENCY or 1), 1))
        tasks: dict[str, asyncio.Task[NewsSourcePollResult]] = {}
        async with asyncio.TaskGroup() as task_group:
            for spec in source_specs:
                tasks[spec.source_code] = task_group.create_task(self._poll_single_source(spec, semaphore=semaphore))
        return {source_code: task.result() for source_code, task in tasks.items()}

    async def _poll_single_source(
        self,
        spec: NewsSourcePollSpec,
        *,
        semaphore: asyncio.Semaphore,
    ) -> NewsSourcePollResult:
        if not spec.enabled:
            return NewsSourcePollResult(
                source_code=spec.source_code,
                status="SKIPPED",
                message=spec.skip_message,
                counts={"skipped": 1},
                items=[],
            )
        cooldown = news_runtime_service.get_source_cooldown(spec.source_code)
        if cooldown.get("active"):
            remaining_seconds = int(cooldown.get("remaining_seconds") or 0)
            remaining_minutes = max(1, remaining_seconds // 60) if remaining_seconds else 1
            return NewsSourcePollResult(
                source_code=spec.source_code,
                status="SKIPPED",
                message=f"연속 실패로 약 {remaining_minutes}분 cooldown 중",
                counts={"skipped": 1},
                items=[],
            )
        try:
            async with semaphore:
                items = await spec.fetch()
        except Exception as exc:
            await error_capture_service.capture_exception(
                component="news_polling",
                operation=f"poll_source:{spec.source_code}",
                exc=exc,
                detail={"source_code": spec.source_code},
            )
            return NewsSourcePollResult(
                source_code=spec.source_code,
                status="ERROR",
                message=str(exc),
                counts=None,
                items=[],
            )
        return NewsSourcePollResult(
            source_code=spec.source_code,
            status="SUCCESS" if items else "EMPTY",
            message="신규 뉴스 반영 완료" if items else "조회된 데이터 없음",
            counts={"received": len(items), "created": 0, "duplicates": 0, "skipped": 0},
            items=items,
        )

    @staticmethod
    def _merge_runtime_counts(base_counts: dict[str, int], source_summary: dict[str, int] | None) -> dict[str, int]:
        counts = {
            "received": int(base_counts.get("received") or 0),
            "created": int(base_counts.get("created") or 0),
            "duplicates": int(base_counts.get("duplicates") or 0),
            "skipped": int(base_counts.get("skipped") or 0),
        }
        if not source_summary:
            return counts
        for key in ("received", "created", "duplicates", "skipped"):
            counts[key] = int(source_summary.get(key) or 0)
        return counts

    @staticmethod
    def _resolve_runtime_status(result: NewsSourcePollResult, counts: dict[str, int]) -> str:
        if result.status in {"ERROR", "SKIPPED"}:
            return result.status
        if int(counts.get("received") or 0) <= 0:
            return "EMPTY"
        return "SUCCESS"

    @staticmethod
    def _build_source_runtime_message(result: NewsSourcePollResult, counts: dict[str, int]) -> str:
        if result.status in {"ERROR", "SKIPPED"}:
            return result.message
        received = int(counts.get("received") or 0)
        created = int(counts.get("created") or 0)
        duplicates = int(counts.get("duplicates") or 0)
        skipped = int(counts.get("skipped") or 0)
        if received <= 0:
            return "조회된 데이터 없음"
        if created > 0:
            return f"신규 {created}건 적재 · 중복 {duplicates}건 · 스킵 {skipped}건"
        if duplicates > 0:
            return f"신규 없음 · 기존 기사 중복 {duplicates}건"
        if skipped > 0:
            return f"신규 없음 · 스킵 {skipped}건"
        return "신규 반영 없음"

    @staticmethod
    def _resolve_overall_status(summary: dict[str, Any], *, source_error_count: int) -> str:
        if source_error_count:
            return "PARTIAL_ERROR"
        if int(summary.get("received") or 0) <= 0:
            return "EMPTY"
        return "SUCCESS"

    @staticmethod
    def _build_overall_runtime_message(summary: dict[str, Any], *, source_error_count: int) -> str:
        created = int(summary.get("created") or 0)
        duplicates = int(summary.get("duplicates") or 0)
        skipped = int(summary.get("skipped") or 0)
        received = int(summary.get("received") or 0)
        if source_error_count:
            return (
                f"일부 소스 실패 · 신규 {created}건 · 중복 {duplicates}건 · "
                f"스킵 {skipped}건 · 오류 {source_error_count}건"
            )
        if received <= 0:
            return "조회된 데이터 없음"
        if created > 0:
            return f"신규 {created}건 적재 · 중복 {duplicates}건 · 스킵 {skipped}건"
        if duplicates > 0:
            return f"신규 없음 · 기존 기사 중복 {duplicates}건"
        if skipped > 0:
            return f"신규 없음 · 스킵 {skipped}건"
        return "신규 반영 없음"


news_polling_service = NewsPollingService()
