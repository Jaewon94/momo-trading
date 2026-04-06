"""자동 뉴스 폴링 + 신규 뉴스 이벤트 발행."""
from __future__ import annotations

import asyncio
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
from services.krx_kind_disclosure_service import krx_kind_disclosure_service
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
                )
            await self._log_news_activity(
                "🛰 뉴스 자동 수집 스킵 · NEWS_POLL_ENABLED 비활성",
                detail={"mode": runtime_mode, "reason": summary["reason"]},
            )
            return summary
        source_results = await self._poll_enabled_sources(source_specs)
        all_items: list[dict[str, Any]] = []
        for spec in source_specs:
            result = source_results[spec.source_code]
            news_runtime_service.record_source_result(
                spec.source_code,
                status=result.status,
                mode=runtime_mode,
                message=result.message,
                counts=result.counts,
            )
            all_items.extend(result.items)

        detailed = await news_ingest_service.ingest_items_detailed(session, all_items)
        summary = dict(detailed["summary"])
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
            counts = result.counts or {}
            source_briefs.append({
                "source_code": spec.source_code,
                "status": result.status,
                "received": int(counts.get("received") or 0),
                "created": int(counts.get("created") or 0),
                "duplicates": int(counts.get("duplicates") or 0),
                "skipped": int(counts.get("skipped") or 0),
                "message": result.message,
            })

        await self._log_news_activity(
            "🛰 뉴스 자동 수집 완료 · "
            f"신규 {int(summary.get('created') or 0)}건 · "
            f"중복 {int(summary.get('duplicates') or 0)}건 · "
            f"스킵 {int(summary.get('skipped') or 0)}건",
            detail={
                "mode": runtime_mode,
                "market_hours": market_hours,
                "summary": summary,
                "published_events": published_events,
                "sources": source_briefs,
            },
        )

        return {
            **summary,
            "published_events": published_events,
            "market_hours": market_hours,
        }

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
        try:
            async with semaphore:
                items = await spec.fetch()
        except Exception as exc:
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


news_polling_service = NewsPollingService()
