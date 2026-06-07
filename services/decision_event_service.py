from __future__ import annotations

import json
from typing import Any

from models.decision_event import DecisionEvent
from repositories.decision_event_repository import DecisionEventRepository
from trading.symbols import normalize_krx_symbol


class DecisionEventService:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from core import database

        return database.AsyncSessionLocal

    async def record_event(
        self,
        *,
        cycle_id: str | None,
        symbol: str,
        stock_name: str | None = None,
        market: str | None = None,
        decision_stage: str,
        source: str,
        strategy_type: str | None = None,
        scanner_score: float | None = None,
        tier1_decision: str | None = None,
        tier2_decision: str | None = None,
        risk_gate_result: str | None = None,
        final_action: str,
        confidence: float | None = None,
        reference_price: float | None = None,
        quantity: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        elapsed_ms: int | None = None,
        status: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DecisionEvent:
        normalized_symbol = normalize_krx_symbol(symbol)
        event = DecisionEvent(
            cycle_id=cycle_id,
            symbol=normalized_symbol,
            stock_name=self._text(stock_name, normalized_symbol),
            market=self._text(market, "KRX").upper(),
            decision_stage=self._text(decision_stage, "UNKNOWN").upper(),
            source=self._text(source, "UNKNOWN"),
            strategy_type=self._optional_text(strategy_type),
            scanner_score=self._optional_float(scanner_score),
            tier1_decision=self._optional_upper(tier1_decision),
            tier2_decision=self._optional_upper(tier2_decision),
            risk_gate_result=self._optional_upper(risk_gate_result),
            final_action=self._text(final_action, "UNKNOWN").upper(),
            confidence=self._optional_float(confidence),
            reference_price=self._optional_float(reference_price),
            quantity=int(quantity) if quantity is not None else None,
            provider=self._text(provider, "UNKNOWN").upper(),
            model=self._text(model, "UNKNOWN"),
            elapsed_ms=int(elapsed_ms) if elapsed_ms is not None else None,
            status=self._text(status, "RECORDED").upper(),
            reason=self._optional_text(reason),
            metadata_json=self._serialize_metadata(metadata),
        )
        async with self.session_factory() as session:
            async with session.begin():
                return await DecisionEventRepository(session).create(event)

    @staticmethod
    def _text(value: str | None, default: str) -> str:
        text = str(value or "").strip()
        return text if text else default

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _optional_upper(value: str | None) -> str | None:
        text = str(value or "").strip()
        return text.upper() if text else None

    @staticmethod
    def _optional_float(value: float | int | str | None) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _serialize_metadata(metadata: dict[str, Any] | None) -> str | None:
        if not metadata:
            return None
        return json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str)


decision_event_service = DecisionEventService()
