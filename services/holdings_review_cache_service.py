"""In-memory cache for repeated intraday holdings review decisions."""
from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass

from core.config import settings
from trading.symbols import normalize_krx_symbol


@dataclass
class HoldingsReviewCacheEntry:
    key: str
    decision: dict
    created_at: float


class HoldingsReviewCacheService:
    def __init__(self) -> None:
        self._entries: dict[str, HoldingsReviewCacheEntry] = {}

    def build_key(
        self,
        *,
        holding_data: dict,
        market_regime: str,
        market_context: str,
        minutes_left: int,
    ) -> str:
        payload = {
            "symbol": normalize_krx_symbol(str(holding_data.get("symbol", ""))),
            "stock_name": str(holding_data.get("stock_name", "")),
            "strategy_type": str(holding_data.get("strategy_type", "")).upper(),
            "avg_price": round(float(holding_data.get("avg_price", 0.0) or 0.0), 2),
            "current_price": round(float(holding_data.get("current_price", 0.0) or 0.0), 2),
            "pnl_rate": round(float(holding_data.get("pnl_rate", 0.0) or 0.0), 3),
            "quantity": int(holding_data.get("quantity", 0) or 0),
            "hold_days": int(holding_data.get("hold_days", 0) or 0),
            "max_hold_days": int(holding_data.get("max_hold_days", 0) or 0),
            "ai_confidence": round(float(holding_data.get("confidence", 0.0) or 0.0), 3),
            "target_price": self._optional_round(holding_data.get("target_price"), 2),
            "stop_loss_price": self._optional_round(holding_data.get("stop_loss_price"), 2),
            "active_stop_loss": self._optional_round(holding_data.get("active_stop_loss"), 2),
            "active_take_profit": self._optional_round(holding_data.get("active_take_profit"), 2),
            "market_regime": str(market_regime or "").upper(),
            "market_context_hash": self._hash_text(market_context),
            "minutes_left_bucket": self._minutes_left_bucket(minutes_left),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict | None:
        if not getattr(settings, "HOLDINGS_REVIEW_CACHE_ENABLED", True):
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        ttl_sec = max(int(getattr(settings, "HOLDINGS_REVIEW_CACHE_TTL_SEC", 1800) or 1800), 1)
        if time.monotonic() - entry.created_at > ttl_sec:
            self._entries.pop(key, None)
            return None
        return copy.deepcopy(entry.decision)

    def put(self, key: str, decision: dict | None) -> None:
        if not getattr(settings, "HOLDINGS_REVIEW_CACHE_ENABLED", True):
            return
        if not decision:
            return
        self._entries[key] = HoldingsReviewCacheEntry(
            key=key,
            decision=copy.deepcopy(decision),
            created_at=time.monotonic(),
        )

    def clear(self) -> None:
        self._entries.clear()

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _minutes_left_bucket(minutes_left: int) -> int:
        bucket_min = max(
            int(getattr(settings, "HOLDINGS_REVIEW_CACHE_MINUTES_LEFT_BUCKET_MIN", 15) or 15),
            1,
        )
        value = max(int(minutes_left or 0), 0)
        return (value // bucket_min) * bucket_min

    @staticmethod
    def _optional_round(value, digits: int) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return None


holdings_review_cache_service = HoldingsReviewCacheService()
