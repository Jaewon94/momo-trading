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
    sources: set[str] = field(default_factory=set)
    hold_candidate: bool = False
    buyable: bool = True


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
    ) -> list[dict[str, Any]]:
        candidates: dict[str, _Candidate] = {}

        self._merge_rows(candidates, volume_rank or [], source="volume_rank")
        self._merge_rows(candidates, surge_data or [], source="surge_data")
        self._merge_rows(candidates, drop_data or [], source="drop_data")
        self._merge_holdings(candidates, holdings or [])

        for candidate in candidates.values():
            if candidate.hold_candidate:
                candidate.score += 30.0
                candidate.reasons.append("보유 종목")
            if "volume_rank" in candidate.sources:
                candidate.score += 25.0
                candidate.reasons.append("거래량 상위")
            if "surge_data" in candidate.sources:
                candidate.score += 20.0
                candidate.reasons.append("급등 상위")
            if "drop_data" in candidate.sources:
                candidate.score -= 10.0
                candidate.reasons.append("급락 감시")

            candidate.score += min(max(candidate.change_rate, -30.0), 30.0)
            candidate.score += min(candidate.volume / 1_000_000, 20.0)

            if candidate.price > 0 and available_cash > 0 and candidate.price > available_cash:
                candidate.buyable = False
                candidate.score -= 100.0
                candidate.reasons.append("1주 매수 불가")

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                not item.buyable,
                -item.score,
                item.symbol,
            ),
        )
        selected = ranked[:max(int(max_candidates or 0), 0)]
        return [
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
                "reasons": item.reasons[:4],
            }
            for item in selected
        ]

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


candidate_scoring_service = CandidateScoringService()

