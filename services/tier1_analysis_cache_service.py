"""In-memory cache for repeated Tier1 analysis under equivalent conditions."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Any

from analysis.chart_analyzer import ChartAnalysisResult
from core.config import settings
from trading.symbols import normalize_krx_symbol


@dataclass
class Tier1AnalysisCacheEntry:
    key: str
    analysis: dict
    created_at: float


class Tier1AnalysisCacheService:
    def __init__(self) -> None:
        self._entries: dict[str, Tier1AnalysisCacheEntry] = {}

    def build_key(
        self,
        *,
        symbol: str,
        strategy_type: str,
        current_price: float,
        chart_result: ChartAnalysisResult,
        portfolio_snapshot: dict | None,
        market_regime: str,
        feedback_context: str,
        news_context: str = "",
    ) -> str:
        signal_summary = chart_result.signal_summary or {}
        indicators = chart_result.indicators or {}
        holding_symbols = {
            normalize_krx_symbol(item)
            for item in (portfolio_snapshot or {}).get("holding_symbols", [])
        }
        payload = {
            "symbol": normalize_krx_symbol(symbol),
            "strategy_type": str(strategy_type or "").upper(),
            "price_bucket": self._price_bucket(current_price),
            "market_regime": str(market_regime or "").upper(),
            "is_holding": normalize_krx_symbol(symbol) in holding_symbols,
            "direction": str(signal_summary.get("direction", "") or "").upper(),
            "signal_confidence": round(float(signal_summary.get("confidence", 0.0) or 0.0), 3),
            "net_score": round(float(signal_summary.get("net_score", 0.0) or 0.0), 2),
            "rsi_14": self._optional_round(indicators.get("rsi_14"), 2),
            "macd_histogram": self._optional_round(indicators.get("macd_histogram"), 4),
            "feedback_hash": self._hash_text(feedback_context),
            "news_hash": self._hash_text(news_context),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict | None:
        if not getattr(settings, "TIER1_ANALYSIS_CACHE_ENABLED", True):
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        ttl_sec = max(int(getattr(settings, "TIER1_ANALYSIS_CACHE_TTL_SEC", 180) or 180), 1)
        if time.monotonic() - entry.created_at > ttl_sec:
            self._entries.pop(key, None)
            return None
        return copy.deepcopy(entry.analysis)

    def put(self, key: str, analysis: dict | None) -> None:
        if not getattr(settings, "TIER1_ANALYSIS_CACHE_ENABLED", True):
            return
        if not analysis:
            return
        self._entries[key] = Tier1AnalysisCacheEntry(
            key=key,
            analysis=copy.deepcopy(analysis),
            created_at=time.monotonic(),
        )

    def clear(self) -> None:
        self._entries.clear()

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _optional_round(value: Any, digits: int) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _price_bucket(price: float) -> int | float:
        numeric_price = float(price or 0.0)
        bucket_bps = max(int(getattr(settings, "TIER1_ANALYSIS_CACHE_PRICE_BUCKET_BPS", 30) or 0), 0)
        if numeric_price <= 0 or bucket_bps <= 0:
            return round(numeric_price, 2)
        return round(math.log(numeric_price) / math.log1p(bucket_bps / 10_000.0))


tier1_analysis_cache_service = Tier1AnalysisCacheService()
