"""종목 분석 프롬프트용 뉴스 보조 컨텍스트."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from repositories.news_item_repository import NewsItemRepository
from strategy.horizon_scan_policy import normalize_scan_horizon
from strategy.news_intelligence_policy import news_horizon_policy
from trading.symbols import normalize_krx_symbol
from util.time_util import ensure_kst, now_kst


class NewsContextService:
    """LLM 매매 판단에 넣을 가벼운 뉴스 보조 정보를 만든다."""

    _MAX_PROMPT_ITEMS = 3

    async def build_for_symbol(
        self,
        session: AsyncSession,
        *,
        symbol: str,
        name: str | None = None,
        max_items: int | None = None,
        horizon: str | None = None,
        lookback_hours: int | None = None,
    ) -> dict[str, Any]:
        normalized_symbol = normalize_krx_symbol(symbol)
        horizon_key = normalize_scan_horizon(horizon) if horizon else ""
        profile = news_horizon_policy(horizon_key) if horizon_key else None
        item_limit = max(int(max_items or (profile.prompt_items if profile else self._MAX_PROMPT_ITEMS)), 1)
        resolved_lookback_hours = max(
            int(
                lookback_hours
                or (profile.lookback_hours if profile else None)
                or settings.NEWS_LOOKBACK_HOURS
                or 24
            ),
            1,
        )
        cutoff = now_kst() - timedelta(hours=resolved_lookback_hours)
        repo = NewsItemRepository(session)

        direct_items = await repo.get_recent(
            limit=max(int(settings.NEWS_MAX_ITEMS_PER_SYMBOL or 20), item_limit),
            symbol=normalized_symbol,
            published_from=cutoff,
        )
        matched_items = list(direct_items)
        match_source = "symbol"

        # 국내 공시/거래소 뉴스는 symbols_csv가 비어 있는 경우가 많아서 종목명으로 보수적 보강한다.
        fallback_name = str(name or "").strip()
        if len(matched_items) < item_limit and len(fallback_name) >= 2:
            name_items = await repo.get_recent(
                limit=item_limit * 3,
                query=fallback_name,
                published_from=cutoff,
            )
            seen = {getattr(item, "id", None) for item in matched_items}
            for item in name_items:
                if getattr(item, "id", None) in seen:
                    continue
                if not self._is_reasonable_name_match(item, fallback_name):
                    continue
                matched_items.append(item)
                seen.add(getattr(item, "id", None))
                match_source = "symbol_or_name"
                if len(matched_items) >= item_limit:
                    break

        items = matched_items[:item_limit]
        if not items:
            prompt = (
                f"### {horizon_key + ' ' if horizon_key else '최근 '}뉴스 보조 컨텍스트\n"
                f"- 최근 {resolved_lookback_hours}시간 내 직접 연결된 뉴스 없음\n"
                f"- 뉴스 판단: 중립. 차트, 수급, 리스크:보상, 매매 상황을 우선 판단하세요.\n"
                f"- 신뢰도 보정 가이드: 뉴스만으로 신뢰도를 올리거나 낮추지 마세요."
            )
            return {
                "available": False,
                "symbol": normalized_symbol,
                "horizon": horizon_key or None,
                "match_source": "none",
                "lookback_hours": resolved_lookback_hours,
                "tone": "NO_RECENT_NEWS",
                "confidence_hint": 0.0,
                "items": [],
                "prompt": prompt,
            }

        formatted_items = [self._format_item(item, fallback_name, normalized_symbol) for item in items]
        negative_count = sum(1 for item in formatted_items if item["sentiment"] == "NEGATIVE")
        positive_count = sum(1 for item in formatted_items if item["sentiment"] == "POSITIVE")
        neutral_count = len(formatted_items) - negative_count - positive_count
        negative_pressure = self._estimate_negative_pressure(formatted_items)
        confidence_hint = self._confidence_hint(
            negative_pressure=negative_pressure,
            negative_count=negative_count,
            positive_count=positive_count,
        )
        tone = self._tone(
            negative_pressure=negative_pressure,
            negative_count=negative_count,
            positive_count=positive_count,
        )
        prompt = self._build_prompt(
            horizon=horizon_key,
            lookback_hours=resolved_lookback_hours,
            items=formatted_items,
            tone=tone,
            negative_pressure=negative_pressure,
            confidence_hint=confidence_hint,
        )
        return {
            "available": True,
            "symbol": normalized_symbol,
            "horizon": horizon_key or None,
            "match_source": match_source,
            "lookback_hours": resolved_lookback_hours,
            "tone": tone,
            "negative_pressure": negative_pressure,
            "negative_count": negative_count,
            "positive_count": positive_count,
            "neutral_count": neutral_count,
            "confidence_hint": confidence_hint,
            "items": formatted_items,
            "prompt": prompt,
        }

    @staticmethod
    def _is_reasonable_name_match(item: Any, name: str) -> bool:
        haystack = " ".join(
            [
                str(getattr(item, "title", "") or ""),
                str(getattr(item, "summary", "") or ""),
                str(getattr(item, "body", "") or ""),
            ]
        )
        if name not in haystack:
            return False
        source_code = str(getattr(item, "source_code", "") or "").upper()
        region = str(getattr(item, "region", "") or "").upper()
        return region == "KR" or source_code in {"DART", "KRX", "YONHAP"}

    def _format_item(self, item: Any, fallback_name: str, symbol: str) -> dict[str, Any]:
        metadata = self._load_metadata(item)
        published_at = ensure_kst(getattr(item, "published_at"))
        sentiment = str(getattr(item, "sentiment_label", "") or "NEUTRAL").upper()
        if sentiment not in {"POSITIVE", "NEGATIVE"}:
            sentiment = "NEUTRAL"
        title = (
            str(metadata.get("translated_title") or "").strip()
            or str(getattr(item, "title", "") or "").strip()
            or "제목 없음"
        )
        summary = (
            str(metadata.get("translated_summary") or "").strip()
            or str(getattr(item, "summary", "") or "").strip()
        )
        symbols_csv = str(getattr(item, "symbols_csv", "") or "")
        match_type = "symbol" if symbol and f",{symbol}," in symbols_csv else "name"
        if fallback_name and fallback_name in title and match_type != "symbol":
            match_type = "name" if match_type != "symbol" else "symbol_or_name"
        return {
            "title": title[:160],
            "summary": summary[:180],
            "source_code": str(getattr(item, "source_code", "") or "").upper(),
            "source_name": str(getattr(item, "source_name", "") or ""),
            "source_tier": str(getattr(item, "source_tier", "") or ""),
            "official": bool(getattr(item, "official", False)),
            "published_at": published_at.isoformat(),
            "age_hours": round(max((now_kst() - published_at).total_seconds() / 3600.0, 0.0), 2),
            "sentiment": sentiment,
            "sentiment_score": round(float(getattr(item, "sentiment_score", 0.5) or 0.5), 4),
            "impact_score": round(float(getattr(item, "impact_score", 0.0) or 0.0), 4),
            "trust_score": round(float(getattr(item, "trust_score", 0.0) or 0.0), 4),
            "match_type": match_type,
        }

    @staticmethod
    def _load_metadata(item: Any) -> dict[str, Any]:
        raw = getattr(item, "metadata_json", None)
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _estimate_negative_pressure(items: list[dict[str, Any]]) -> float:
        pressure = 0.0
        for item in items:
            if item["sentiment"] != "NEGATIVE":
                continue
            score = min(max(float(item.get("sentiment_score") or 0.5), 0.0), 1.0)
            impact = float(item.get("impact_score") or 0.0) or (0.9 if item.get("official") else 0.45)
            trust = float(item.get("trust_score") or 0.0) or (0.9 if item.get("official") else 0.5)
            freshness = 0.5 ** (float(item.get("age_hours") or 0.0) / 8.0)
            pressure += max(0.0, 0.5 - score) * 2.0 * impact * trust * freshness
        return round(min(pressure, 1.5), 4)

    @staticmethod
    def _confidence_hint(*, negative_pressure: float, negative_count: int, positive_count: int) -> float:
        if negative_pressure >= 0.5:
            return -0.06
        if negative_count > 0:
            return -0.03
        if positive_count > 0:
            return 0.03
        return 0.0

    @staticmethod
    def _tone(*, negative_pressure: float, negative_count: int, positive_count: int) -> str:
        if negative_pressure >= 0.5:
            return "NEGATIVE_CAUTION"
        if negative_count > 0:
            return "MILD_NEGATIVE"
        if positive_count > 0:
            return "POSITIVE_SUPPORT"
        return "NEUTRAL"

    @staticmethod
    def _build_prompt(
        *,
        horizon: str,
        lookback_hours: int,
        items: list[dict[str, Any]],
        tone: str,
        negative_pressure: float,
        confidence_hint: float,
    ) -> str:
        lines = [
            f"### {horizon + ' ' if horizon else '최근 '}뉴스 보조 컨텍스트",
            "- 뉴스 역할: 차트/수급/리스크 판단을 보조합니다. 뉴스만으로 BUY/SELL을 결정하지 마세요.",
            f"- 관측 범위: 최근 {lookback_hours}시간, 최대 {len(items)}건",
            f"- 뉴스 보조 판단: {tone} | 부정 압력 {negative_pressure:.2f} | 신뢰도 힌트 {confidence_hint:+.2f}",
        ]
        for idx, item in enumerate(items, start=1):
            source = item.get("source_name") or item.get("source_code") or "뉴스"
            official = "공식" if item.get("official") else "언론"
            lines.append(
                f"{idx}. [{item['sentiment']}] {item['title']} "
                f"({source}, {official}, {item['age_hours']:.1f}시간 전)"
            )
            if item.get("summary"):
                lines.append(f"   - 요약: {item['summary']}")
        lines.append(
            "- 적용 원칙: 긍정 뉴스는 약한 가산 근거, 부정 뉴스는 리스크 점검 근거입니다. "
            "강한 기술적 근거가 없으면 뉴스로 신뢰도를 억지로 올리지 마세요."
        )
        return "\n".join(lines)


news_context_service = NewsContextService()
