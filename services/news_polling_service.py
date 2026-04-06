"""자동 뉴스 폴링 + 신규 뉴스 이벤트 발행."""
from __future__ import annotations

from core.config import settings
from core.events import Event, EventType, event_bus
from services.bloomberg_news_service import bloomberg_news_service
from services.cnbc_news_service import cnbc_news_service
from services.investing_news_service import investing_news_service
from services.nasdaq_news_service import nasdaq_news_service
from services.news_ingest_service import news_ingest_service
from services.krx_kind_disclosure_service import krx_kind_disclosure_service
from services.open_dart_disclosure_service import open_dart_disclosure_service
from services.news_runtime_service import news_runtime_service
from services.yonhap_news_service import yonhap_news_service


class NewsPollingService:
    async def poll_sources(self, session, *, market_hours: bool) -> dict:
        if not settings.NEWS_POLL_ENABLED:
            summary = {"skipped": True, "reason": "NEWS_POLL_ENABLED disabled"}
            news_runtime_service.record_source_result(
                "DART",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message=summary["reason"],
                counts=summary,
            )
            news_runtime_service.record_source_result(
                "KRX",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message=summary["reason"],
                counts=summary,
            )
            news_runtime_service.record_source_result(
                "YONHAP",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message=summary["reason"],
                counts=summary,
            )
            news_runtime_service.record_source_result(
                "BLOOMBERG",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message=summary["reason"],
                counts=summary,
            )
            news_runtime_service.record_source_result(
                "CNBC",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message=summary["reason"],
                counts=summary,
            )
            news_runtime_service.record_source_result(
                "NASDAQ",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message=summary["reason"],
                counts=summary,
            )
            news_runtime_service.record_source_result(
                "INVESTING",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message=summary["reason"],
                counts=summary,
            )
            return summary
        all_items = []
        page_count = max(int(settings.NEWS_POLL_PAGE_COUNT or 25), 1)

        if settings.OPEN_DART_API_KEY:
            try:
                dart_items = await open_dart_disclosure_service.fetch_recent_disclosures(
                    days=1,
                    page_count=page_count,
                )
                news_runtime_service.record_source_result(
                    "DART",
                    status="SUCCESS" if dart_items else "EMPTY",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message="신규 뉴스 반영 완료" if dart_items else "조회된 데이터 없음",
                    counts={"received": len(dart_items), "created": 0, "duplicates": 0, "skipped": 0},
                )
                all_items.extend(dart_items)
            except Exception as exc:
                news_runtime_service.record_source_result(
                    "DART",
                    status="ERROR",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message=str(exc),
                )
        else:
            news_runtime_service.record_source_result(
                "DART",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message="OPEN_DART_API_KEY missing",
                counts={"skipped": 1},
            )

        try:
            krx_items = await krx_kind_disclosure_service.fetch_recent_disclosures(page_count=page_count)
            news_runtime_service.record_source_result(
                "KRX",
                status="SUCCESS" if krx_items else "EMPTY",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message="신규 뉴스 반영 완료" if krx_items else "조회된 데이터 없음",
                counts={"received": len(krx_items), "created": 0, "duplicates": 0, "skipped": 0},
            )
            all_items.extend(krx_items)
        except Exception as exc:
            news_runtime_service.record_source_result(
                "KRX",
                status="ERROR",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message=str(exc),
            )

        if settings.NEWS_DOMESTIC_MEDIA_ENABLED:
            try:
                yonhap_items = await yonhap_news_service.fetch_recent_news(
                    session,
                    limit=page_count,
                )
                news_runtime_service.record_source_result(
                    "YONHAP",
                    status="SUCCESS" if yonhap_items else "EMPTY",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message="신규 뉴스 반영 완료" if yonhap_items else "조회된 데이터 없음",
                    counts={"received": len(yonhap_items), "created": 0, "duplicates": 0, "skipped": 0},
                )
                all_items.extend(yonhap_items)
            except Exception as exc:
                news_runtime_service.record_source_result(
                    "YONHAP",
                    status="ERROR",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message=str(exc),
                )
        else:
            news_runtime_service.record_source_result(
                "YONHAP",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message="NEWS_DOMESTIC_MEDIA_ENABLED disabled",
                counts={"skipped": 1},
            )

        if settings.NEWS_INCLUDE_FOREIGN:
            try:
                bloomberg_items = await bloomberg_news_service.fetch_recent_news(
                    limit=page_count,
                )
                news_runtime_service.record_source_result(
                    "BLOOMBERG",
                    status="SUCCESS" if bloomberg_items else "EMPTY",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message="신규 뉴스 반영 완료" if bloomberg_items else "조회된 데이터 없음",
                    counts={"received": len(bloomberg_items), "created": 0, "duplicates": 0, "skipped": 0},
                )
                all_items.extend(bloomberg_items)
            except Exception as exc:
                news_runtime_service.record_source_result(
                    "BLOOMBERG",
                    status="ERROR",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message=str(exc),
                )
            try:
                cnbc_items = await cnbc_news_service.fetch_recent_news(
                    limit=page_count,
                )
                news_runtime_service.record_source_result(
                    "CNBC",
                    status="SUCCESS" if cnbc_items else "EMPTY",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message="신규 뉴스 반영 완료" if cnbc_items else "조회된 데이터 없음",
                    counts={"received": len(cnbc_items), "created": 0, "duplicates": 0, "skipped": 0},
                )
                all_items.extend(cnbc_items)
            except Exception as exc:
                news_runtime_service.record_source_result(
                    "CNBC",
                    status="ERROR",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message=str(exc),
                )
            if settings.NEWS_NASDAQ_ENABLED:
                try:
                    nasdaq_items = await nasdaq_news_service.fetch_recent_news(
                        limit=page_count,
                    )
                    news_runtime_service.record_source_result(
                        "NASDAQ",
                        status="SUCCESS" if nasdaq_items else "EMPTY",
                        mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                        message="신규 뉴스 반영 완료" if nasdaq_items else "조회된 데이터 없음",
                        counts={"received": len(nasdaq_items), "created": 0, "duplicates": 0, "skipped": 0},
                    )
                    all_items.extend(nasdaq_items)
                except Exception as exc:
                    news_runtime_service.record_source_result(
                        "NASDAQ",
                        status="ERROR",
                        mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                        message=str(exc),
                    )
            else:
                news_runtime_service.record_source_result(
                    "NASDAQ",
                    status="SKIPPED",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message="NEWS_NASDAQ_ENABLED disabled",
                    counts={"skipped": 1},
                )
            try:
                investing_items = await investing_news_service.fetch_recent_news(
                    limit=page_count,
                )
                news_runtime_service.record_source_result(
                    "INVESTING",
                    status="SUCCESS" if investing_items else "EMPTY",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message="신규 뉴스 반영 완료" if investing_items else "조회된 데이터 없음",
                    counts={"received": len(investing_items), "created": 0, "duplicates": 0, "skipped": 0},
                )
                all_items.extend(investing_items)
            except Exception as exc:
                news_runtime_service.record_source_result(
                    "INVESTING",
                    status="ERROR",
                    mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                    message=str(exc),
                )
        else:
            news_runtime_service.record_source_result(
                "BLOOMBERG",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message="NEWS_INCLUDE_FOREIGN disabled",
                counts={"skipped": 1},
            )
            news_runtime_service.record_source_result(
                "CNBC",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message="NEWS_INCLUDE_FOREIGN disabled",
                counts={"skipped": 1},
            )
            news_runtime_service.record_source_result(
                "NASDAQ",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message="NEWS_INCLUDE_FOREIGN disabled",
                counts={"skipped": 1},
            )
            news_runtime_service.record_source_result(
                "INVESTING",
                status="SKIPPED",
                mode="AUTO_TRADING" if market_hours else "AUTO_OFF_HOURS",
                message="NEWS_INCLUDE_FOREIGN disabled",
                counts={"skipped": 1},
            )

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

        return {
            **summary,
            "published_events": published_events,
            "market_hours": market_hours,
        }


news_polling_service = NewsPollingService()
