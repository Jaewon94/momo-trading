"""Deterministic candidate scoring before market-scan LLM selection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Candidate:
    symbol: str
    name: str
    price: float
    change_rate: float
    volume: int
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    reason_codes: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    hold_candidate: bool = False
    buyable: bool = True
    policy_buy_eligible: bool = True


class CandidateScoringService:
    def score_candidates(
        self,
        *,
        volume_rank: list[dict] | None,
        surge_data: list[dict] | None,
        drop_data: list[dict] | None,
        holdings: list[Any] | None,
        available_cash: float,
        max_candidates: int = 8,
        cooldown_symbols: set[str] | None = None,
        news_pressure_by_symbol: dict[str, float] | None = None,
        preferred_change_min_pct: float | None = None,
        preferred_change_max_pct: float | None = None,
    ) -> list[dict[str, Any]]:
        candidates: dict[str, _Candidate] = {}
        cooldown_set = {str(symbol).strip() for symbol in (cooldown_symbols or set()) if str(symbol).strip()}
        news_pressure = {
            str(symbol).strip(): float(value or 0.0)
            for symbol, value in (news_pressure_by_symbol or {}).items()
            if str(symbol).strip()
        }
        preferred_min = self._positive_or_none(preferred_change_min_pct)
        preferred_max = self._positive_or_none(preferred_change_max_pct)

        self._merge_rows(candidates, volume_rank or [], source="volume_rank")
        self._merge_rows(candidates, surge_data or [], source="surge_data")
        self._merge_rows(candidates, drop_data or [], source="drop_data")
        self._merge_holdings(candidates, holdings or [])

        for candidate in candidates.values():
            if candidate.hold_candidate:
                candidate.score += 30.0
                candidate.reasons.append("보유 종목")
                candidate.reason_codes.add("HOLDING_REVIEW")
            if "volume_rank" in candidate.sources:
                candidate.score += 25.0
                candidate.reasons.append("거래량 상위")
                candidate.reason_codes.add("VOLUME_RANK")
            if "surge_data" in candidate.sources:
                candidate.score += 20.0
                candidate.reasons.append("급등 상위")
                candidate.reason_codes.add("SURGE_RANK")
            if "drop_data" in candidate.sources:
                candidate.score -= 10.0
                candidate.reasons.append("급락 감시")
                candidate.reason_codes.add("DROP_WATCH")

            candidate.score += min(max(candidate.change_rate, -30.0), 30.0)
            candidate.score += min(candidate.volume / 1_000_000, 20.0)
            if not candidate.hold_candidate:
                self._apply_policy_change_band(
                    candidate,
                    preferred_min=preferred_min,
                    preferred_max=preferred_max,
                )

            if candidate.price > 0 and available_cash > 0 and candidate.price > available_cash:
                candidate.buyable = False
                candidate.policy_buy_eligible = False
                candidate.score -= 100.0
                candidate.reasons.append("1주 매수 불가")
                candidate.reason_codes.add("NOT_BUYABLE")
            if candidate.symbol in cooldown_set and not candidate.hold_candidate:
                candidate.score -= 35.0
                candidate.reasons.append("최근 분석/후보 감점")
                candidate.reason_codes.add("RECENT_CANDIDATE_COOLDOWN")
            pressure = max(float(news_pressure.get(candidate.symbol) or 0.0), 0.0)
            if pressure >= 0.25 and not candidate.hold_candidate:
                penalty = min(max(pressure * 40.0, 10.0), 45.0)
                candidate.score -= penalty
                candidate.reasons.append(f"뉴스 부정압력 {pressure:.2f}")
                candidate.reason_codes.add("NEGATIVE_NEWS_PRESSURE")

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                not item.buyable,
                -item.score,
                item.symbol,
            ),
        )
        selected = ranked[:max(int(max_candidates or 0), 0)]
        results: list[dict[str, Any]] = []
        for item in selected:
            pressure = round(max(float(news_pressure.get(item.symbol) or 0.0), 0.0), 4)
            results.append(
                {
                    "symbol": item.symbol,
                    "name": item.name,
                    "price": item.price,
                    "change_rate": round(item.change_rate, 2),
                    "volume": item.volume,
                    "score": round(item.score, 2),
                    "sources": sorted(item.sources),
                    "buyable": item.buyable,
                    "hold_candidate": item.hold_candidate,
                    "policy_buy_eligible": item.policy_buy_eligible,
                    "strategy_type_hint": self._strategy_type_hint(item, pressure),
                    "reason_codes": sorted(item.reason_codes),
                    "news_negative_pressure": pressure,
                    "reasons": item.reasons[:4],
                }
            )
        return results

    @staticmethod
    def _strategy_type_hint(candidate: _Candidate, news_pressure: float) -> str:
        if candidate.hold_candidate or not candidate.buyable:
            return "STABLE_SHORT"
        if news_pressure >= 0.5:
            return "STABLE_SHORT"
        if (
            "surge_data" in candidate.sources
            and "volume_rank" in candidate.sources
            and 6.0 <= abs(candidate.change_rate) <= 10.0
            and candidate.score >= 50.0
            and news_pressure < 0.25
        ):
            return "AGGRESSIVE_SHORT"
        return "STABLE_SHORT"

    @staticmethod
    def _apply_policy_change_band(
        candidate: _Candidate,
        *,
        preferred_min: float | None,
        preferred_max: float | None,
    ) -> None:
        if preferred_min is not None and candidate.change_rate < preferred_min:
            gap = preferred_min - candidate.change_rate
            candidate.policy_buy_eligible = False
            candidate.score -= min(35.0, 8.0 + gap * 2.0)
            candidate.reasons.append(f"정책 모멘텀 부족 ({candidate.change_rate:.2f}% < {preferred_min:.2f}%)")
            candidate.reason_codes.add("POLICY_CHANGE_BELOW_MIN")
        if preferred_max is not None and candidate.change_rate > preferred_max:
            excess = candidate.change_rate - preferred_max
            candidate.policy_buy_eligible = False
            candidate.score -= min(70.0, 18.0 + excess * 3.0)
            candidate.reasons.append(f"정책 과열 제외 ({candidate.change_rate:.2f}% > {preferred_max:.2f}%)")
            candidate.reason_codes.add("POLICY_CHANGE_OVER_MAX")
        if (
            candidate.policy_buy_eligible
            and preferred_min is not None
            and preferred_max is not None
            and preferred_min <= candidate.change_rate <= preferred_max
        ):
            candidate.score += 8.0
            candidate.reasons.append("정책 적합 모멘텀")
            candidate.reason_codes.add("POLICY_CHANGE_WINDOW")

    @staticmethod
    def _merge_rows(candidates: dict[str, _Candidate], rows: list[dict], *, source: str) -> None:
        for row in rows:
            symbol = str(row.get("symbol", row.get("code", "")) or "").strip()
            name = str(row.get("name", row.get("stock_name", symbol)) or symbol).strip()
            if not symbol or not name:
                continue
            price = CandidateScoringService._to_float(row.get("price", row.get("current_price", 0.0)))
            change_rate = CandidateScoringService._to_float(row.get("change_rate", 0.0))
            volume = CandidateScoringService._to_int(row.get("volume", 0))
            item = candidates.get(symbol)
            if item is None:
                item = _Candidate(
                    symbol=symbol,
                    name=name,
                    price=price,
                    change_rate=change_rate,
                    volume=volume,
                )
                candidates[symbol] = item
            else:
                item.price = max(item.price, price)
                if abs(change_rate) > abs(item.change_rate):
                    item.change_rate = change_rate
                item.volume = max(item.volume, volume)
            item.sources.add(source)

    @staticmethod
    def _merge_holdings(candidates: dict[str, _Candidate], holdings: list[Any]) -> None:
        for row in holdings:
            symbol = str(getattr(row, "symbol", "") or "").strip()
            name = str(getattr(row, "name", symbol) or symbol).strip()
            if not symbol or not name:
                continue
            item = candidates.get(symbol)
            if item is None:
                item = _Candidate(
                    symbol=symbol,
                    name=name,
                    price=float(getattr(row, "current_price", 0.0) or 0.0),
                    change_rate=float(getattr(row, "pnl_rate", 0.0) or 0.0),
                    volume=0,
                )
                candidates[symbol] = item
            item.hold_candidate = True
            item.sources.add("holdings")

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _positive_or_none(value: float | int | str | None) -> float | None:
        try:
            parsed = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None


candidate_scoring_service = CandidateScoringService()
