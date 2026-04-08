"""뉴스 인텔 운영/리포팅 집계 서비스."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.news_item import NewsItem
from services.news_ingest_service import news_ingest_service
from services.performance_reporting_service import performance_reporting_service
from services.news_runtime_service import news_runtime_service
from util.time_util import ensure_kst, now_kst


class NewsReportingService:
    """뉴스 수집/게이트/성과 정보를 운영 UI에 맞게 묶는다."""

    async def build_overview(
        self,
        session: AsyncSession,
        *,
        recent_limit: int = 5,
        performance_days: int = 30,
    ) -> dict:
        source_catalog = news_ingest_service.get_source_catalog(
            include_foreign=bool(settings.NEWS_INCLUDE_FOREIGN)
        )
        implemented_sources = set(news_runtime_service.IMPLEMENTED_SOURCES)
        source_catalog = [
            {
                **item,
                "implemented": item.get("code") in implemented_sources,
            }
            for item in source_catalog
        ]
        allowed_codes = {item["code"] for item in source_catalog}
        storage = {
            "ready": True,
            "message": "news_items 저장소 준비됨",
        }
        recent_items: list[NewsItem] = []
        ingestion = {
            "total_count": 0,
            "recent_24h_count": 0,
            "recent_7d_count": 0,
            "latest_published_at": None,
            "by_source_24h": [],
        }
        try:
            recent_items = await self._fetch_recent_items(
                session,
                allowed_codes=allowed_codes,
                limit=max(int(recent_limit), 1),
            )
            ingestion = await self._build_ingestion_stats(session, allowed_codes=allowed_codes)
        except OperationalError as exc:
            storage = {
                "ready": False,
                "message": str(getattr(exc, "orig", exc)),
            }
        performance = await performance_reporting_service.build_summary(
            session,
            days=max(int(performance_days), 1),
        )
        weekly = await performance_reporting_service.build_periodic_summary(
            session,
            period="weekly",
            size=6,
        )
        monthly = await performance_reporting_service.build_periodic_summary(
            session,
            period="monthly",
            size=6,
        )
        return {
            "baseline": performance.get("baseline") or {},
            "settings": self._build_settings_snapshot(),
            "health": self._build_health_snapshot(ingestion),
            "storage": storage,
            "sources": {
                "enabled_count": len(source_catalog),
                "implemented_count": sum(1 for item in source_catalog if item.get("implemented")),
                "official_count": sum(1 for item in source_catalog if item.get("official")),
                "codes": [item["code"] for item in source_catalog],
                "catalog": source_catalog,
            },
            "ingestion": ingestion,
            "runtime": news_runtime_service.get_snapshot(
                include_foreign=bool(settings.NEWS_INCLUDE_FOREIGN)
            ),
            "recent_items": [news_ingest_service.serialize_item(item) for item in recent_items],
            "performance": {
                "days": max(int(performance_days), 1),
                "window": performance.get("window") or {},
                "overall": performance.get("overall") or {},
                "news_gate_blocks": int((performance.get("risk_controls") or {}).get("news_gate_blocks") or 0),
                "news_rechecks": int((performance.get("risk_controls") or {}).get("news_rechecks") or 0),
                "avg_negative_pressure": float((performance.get("news_context") or {}).get("avg_negative_pressure") or 0.0),
                "trade_count_with_news": int((performance.get("news_context") or {}).get("trade_count") or 0),
                "shadow": performance.get("shadow") or {},
                "rollout": performance.get("rollout") or {},
            },
            "periodic": {
                "weekly": weekly,
                "monthly": monthly,
            },
        }

    @staticmethod
    def _build_settings_snapshot() -> dict:
        return {
            "llm_enabled": bool(settings.NEWS_LLM_ENABLED),
            "llm_provider": str(settings.NEWS_LLM_PROVIDER or "CLAUDE_CODE"),
            "domestic_media_enabled": bool(settings.NEWS_DOMESTIC_MEDIA_ENABLED),
            "include_foreign": bool(settings.NEWS_INCLUDE_FOREIGN),
            "nasdaq_enabled": bool(settings.NEWS_NASDAQ_ENABLED),
            "gate_enabled": bool(settings.NEWS_GATE_ENABLED),
            "poll_enabled": bool(settings.NEWS_POLL_ENABLED),
            "negative_block_threshold": float(settings.NEWS_NEGATIVE_BLOCK_THRESHOLD or 0.0),
            "lookback_hours": int(settings.NEWS_LOOKBACK_HOURS or 0),
            "max_items_per_symbol": int(settings.NEWS_MAX_ITEMS_PER_SYMBOL or 0),
            "shadow_enabled": bool(settings.NEWS_SHADOW_ENABLED),
            "rollout_min_sample_size": int(settings.NEWS_ROLLOUT_MIN_SAMPLE_SIZE or 0),
            "rollout_min_profit_factor": float(settings.NEWS_ROLLOUT_MIN_PROFIT_FACTOR or 0.0),
            "rollout_min_expectancy": float(settings.NEWS_ROLLOUT_MIN_EXPECTANCY or 0.0),
            "rollout_max_drawdown_krw": float(settings.NEWS_ROLLOUT_MAX_DRAWDOWN_KRW or 0.0),
        }

    @staticmethod
    def _build_health_snapshot(ingestion: dict) -> dict:
        alerts: list[str] = []
        if not settings.NEWS_POLL_ENABLED:
            alerts.append("자동 뉴스 폴링 비활성")
        if not settings.NEWS_INCLUDE_FOREIGN and not settings.NEWS_DOMESTIC_MEDIA_ENABLED:
            alerts.append("해외 뉴스와 국내 언론 소스가 모두 비활성")
        if int(ingestion.get("recent_24h_count") or 0) == 0:
            alerts.append("최근 24시간 신규 적재 0건")
        if int(ingestion.get("translation_pending_count") or 0) > 0:
            alerts.append(f"번역 대기 {int(ingestion.get('translation_pending_count') or 0)}건")
        status = "WARN" if alerts else "OK"
        return {
            "status": status,
            "alerts": alerts,
        }

    async def _fetch_recent_items(
        self,
        session: AsyncSession,
        *,
        allowed_codes: set[str],
        limit: int,
    ) -> list[NewsItem]:
        if not allowed_codes:
            return []
        stmt = (
            select(NewsItem)
            .where(NewsItem.source_code.in_(sorted(allowed_codes)))
            .order_by(desc(NewsItem.published_at), desc(NewsItem.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _build_ingestion_stats(
        self,
        session: AsyncSession,
        *,
        allowed_codes: set[str],
    ) -> dict:
        if not allowed_codes:
            return {
                "total_count": 0,
                "recent_24h_count": 0,
                "recent_7d_count": 0,
                "latest_published_at": None,
                "by_source_24h": [],
                "translation_pending_count": 0,
                "translation_failed_count": 0,
            }

        now = now_kst().replace(tzinfo=None)
        since_24h = now - timedelta(hours=24)
        since_7d = now - timedelta(days=7)

        total_stmt = select(func.count(NewsItem.id)).where(
            NewsItem.source_code.in_(sorted(allowed_codes))
        )
        recent_24h_stmt = select(func.count(NewsItem.id)).where(
            NewsItem.source_code.in_(sorted(allowed_codes)),
            NewsItem.published_at >= since_24h,
        )
        recent_7d_stmt = select(func.count(NewsItem.id)).where(
            NewsItem.source_code.in_(sorted(allowed_codes)),
            NewsItem.published_at >= since_7d,
        )
        latest_stmt = select(func.max(NewsItem.published_at)).where(
            NewsItem.source_code.in_(sorted(allowed_codes))
        )
        by_source_stmt = (
            select(NewsItem.source_code, func.count(NewsItem.id))
            .where(
                NewsItem.source_code.in_(sorted(allowed_codes)),
                NewsItem.published_at >= since_24h,
            )
            .group_by(NewsItem.source_code)
            .order_by(func.count(NewsItem.id).desc(), NewsItem.source_code.asc())
        )
        translation_pending_stmt = select(func.count(NewsItem.id)).where(
            NewsItem.source_code.in_(sorted(allowed_codes)),
            NewsItem.metadata_json.like('%"translation_status"%PENDING%'),
        )
        translation_failed_stmt = select(func.count(NewsItem.id)).where(
            NewsItem.source_code.in_(sorted(allowed_codes)),
            NewsItem.metadata_json.like('%"translation_status"%FAILED%'),
        )

        total_count = int((await session.execute(total_stmt)).scalar() or 0)
        recent_24h = int((await session.execute(recent_24h_stmt)).scalar() or 0)
        recent_7d = int((await session.execute(recent_7d_stmt)).scalar() or 0)
        latest_published_at = (await session.execute(latest_stmt)).scalar()
        by_source_rows = (await session.execute(by_source_stmt)).all()
        translation_pending_count = int((await session.execute(translation_pending_stmt)).scalar() or 0)
        translation_failed_count = int((await session.execute(translation_failed_stmt)).scalar() or 0)

        return {
            "total_count": total_count,
            "recent_24h_count": recent_24h,
            "recent_7d_count": recent_7d,
            "latest_published_at": ensure_kst(latest_published_at).isoformat() if latest_published_at else None,
            "by_source_24h": [
                {
                    "source_code": str(source_code),
                    "count": int(count or 0),
                }
                for source_code, count in by_source_rows
            ],
            "translation_pending_count": translation_pending_count,
            "translation_failed_count": translation_failed_count,
        }


news_reporting_service = NewsReportingService()
