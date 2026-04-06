"""뉴스 감성/신뢰도/신선도 기반 매수 게이트."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from repositories.news_item_repository import NewsItemRepository
from scheduler.market_calendar import market_calendar
from util.time_util import ensure_kst, now_kst


class NewsSignalService:
    _HORIZON_PROFILE = {
        "SHORT": {"threshold_multiplier": 0.9, "freshness_multiplier": 0.7},
        "MID": {"threshold_multiplier": 1.0, "freshness_multiplier": 1.0},
        "LONG": {"threshold_multiplier": 1.12, "freshness_multiplier": 1.35},
    }
    _SEVERITY_KEYWORDS: tuple[tuple[str, float], ...] = (
        ("회계 조사", 1.35),
        ("investigation", 1.35),
        ("fraud", 1.35),
        ("분식", 1.35),
        ("부도", 1.3),
        ("default", 1.3),
        ("거래정지", 1.25),
        ("suspension", 1.25),
        ("실적 경고", 1.18),
        ("profit warning", 1.18),
        ("guidance cut", 1.18),
        ("리콜", 1.15),
        ("recall", 1.15),
        ("공급 차질", 1.15),
        ("supply disruption", 1.15),
        ("demand warning", 1.12),
        ("정정 공시", 1.08),
    )

    async def evaluate_gate(
        self,
        session: AsyncSession,
        *,
        symbol: str,
        horizon: str | None = None,
    ) -> dict:
        if not settings.NEWS_GATE_ENABLED:
            return {"approved": True, "reason": "뉴스 게이트 비활성화"}

        repo = NewsItemRepository(session)
        items = await repo.get_recent(
            limit=max(int(settings.NEWS_MAX_ITEMS_PER_SYMBOL or 20), 1),
            symbol=symbol,
        )

        horizon_key = str(horizon or "MID").upper()
        profile = self._HORIZON_PROFILE.get(horizon_key, self._HORIZON_PROFILE["MID"])
        now = now_kst()
        cutoff = now - timedelta(hours=max(int(settings.NEWS_LOOKBACK_HOURS or 24), 1))
        halflife_hours = max(float(settings.NEWS_FRESHNESS_HALFLIFE_HOURS or 8.0), 0.1) * float(profile["freshness_multiplier"])
        contributors: list[dict[str, Any]] = []

        for item in items:
            contributor = self._evaluate_item_pressure(
                item,
                cutoff=cutoff,
                now=now,
                halflife_hours=halflife_hours,
            )
            if contributor is not None:
                contributors.append(contributor)

        contributors.sort(key=lambda item: float(item.get("pressure") or 0.0), reverse=True)
        base_negative_pressure = sum(float(item.get("pressure_base") or 0.0) for item in contributors)
        weighted_negative_pressure = sum(float(item.get("pressure") or 0.0) for item in contributors)
        distinct_sources = len({
            str(item.get("source_code") or "").upper()
            for item in contributors
            if str(item.get("source_code") or "").strip()
        })
        source_diversity_boost = min(1.0 + max(distinct_sources - 1, 0) * 0.08, 1.24)
        negative_pressure = weighted_negative_pressure * source_diversity_boost

        threshold = float(settings.NEWS_NEGATIVE_BLOCK_THRESHOLD or 0.75) * float(profile["threshold_multiplier"])
        approved = negative_pressure < threshold
        headlines = [str(item.get("headline") or "") for item in contributors[:3] if str(item.get("headline") or "").strip()]
        return {
            "approved": approved,
            "reason": (
                f"부정 뉴스 압력 {negative_pressure:.2f} >= {threshold:.2f}"
                if not approved else
                f"부정 뉴스 압력 {negative_pressure:.2f} < {threshold:.2f}"
            ),
            "negative_pressure": round(negative_pressure, 4),
            "negative_pressure_base": round(base_negative_pressure, 4),
            "negative_count": len(contributors),
            "threshold": round(threshold, 4),
            "headlines": headlines,
            "contributors": contributors[:3],
            "source_count": distinct_sources,
            "source_diversity_boost": round(source_diversity_boost, 4),
            "horizon": horizon_key,
        }

    @staticmethod
    def _negative_score(label: str | None, score: float) -> float:
        normalized = str(label or "").upper().strip()
        bounded_score = min(max(float(score or 0.5), 0.0), 1.0)
        base = max(0.0, (0.5 - bounded_score) * 2.0)
        if normalized == "NEGATIVE":
            return min(1.0, 0.55 + base * 0.65)
        return base

    @staticmethod
    def _impact_score(raw_impact: float, official: bool, source_tier: str | None) -> float:
        if raw_impact and raw_impact > 0:
            base = float(raw_impact)
        else:
            normalized_tier = str(source_tier or "").upper().strip()
            if normalized_tier == "A":
                base = 0.82
            elif normalized_tier == "B":
                base = 0.62
            else:
                base = 0.45
        if official:
            base = max(base, 0.9)
        return min(base, 1.0)

    def _evaluate_item_pressure(
        self,
        item,
        *,
        cutoff,
        now,
        halflife_hours: float,
    ) -> dict[str, Any] | None:
        published_at = ensure_kst(item.published_at)
        if published_at < cutoff:
            return None

        negative_score = self._negative_score(item.sentiment_label, float(item.sentiment_score or 0.5))
        if negative_score <= 0:
            return None

        age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
        freshness = 0.5 ** (age_hours / max(halflife_hours, 0.1))
        impact = self._impact_score(item.impact_score, bool(item.official), getattr(item, "source_tier", None))
        trust = max(float(item.trust_score or 0.0), 0.0)
        headline = self._display_headline(item)
        severity = self._severity_multiplier(headline)
        session_multiplier = self._session_multiplier(now=now, published_at=published_at)
        pressure_base = negative_score * freshness * impact * trust * severity
        pressure = pressure_base * session_multiplier

        if pressure <= 0:
            return None

        return {
            "headline": headline,
            "source_code": str(getattr(item, "source_code", "") or "").upper(),
            "published_at": published_at.isoformat(),
            "pressure": round(pressure, 4),
            "freshness": round(freshness, 4),
            "impact": round(impact, 4),
            "trust": round(trust, 4),
            "negative_score": round(negative_score, 4),
            "severity": round(severity, 4),
            "session_multiplier": round(session_multiplier, 4),
            "pressure_base": round(pressure_base, 4),
        }

    @staticmethod
    def _load_metadata(item) -> dict[str, Any]:
        raw = getattr(item, "metadata_json", None)
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _display_headline(self, item) -> str:
        metadata = self._load_metadata(item)
        return (
            str(metadata.get("translated_title") or "").strip()
            or str(getattr(item, "title", "") or "").strip()
            or "뉴스"
        )

    def _severity_multiplier(self, headline: str) -> float:
        text = str(headline or "").lower()
        severity = 1.0
        for keyword, weight in self._SEVERITY_KEYWORDS:
            if keyword.lower() in text:
                severity = max(severity, weight)
        return severity

    @staticmethod
    def _session_multiplier(*, now, published_at) -> float:
        age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
        if age_hours > 12:
            return 1.0
        if market_calendar.is_krx_trading_hours():
            return 1.03 if age_hours <= 1.5 else 1.0
        return 1.08 if age_hours <= 6 else 1.02


news_signal_service = NewsSignalService()
