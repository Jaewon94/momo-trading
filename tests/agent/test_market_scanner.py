import pytest

from agent.market_scanner import MarketScanner
from trading.models import AccountBalance, HoldingInfo


class FakeScannerBrokerAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def get_balance(self) -> AccountBalance:
        self.calls.append(("balance", ""))
        return AccountBalance(
            total_asset=1_500_000,
            cash=900_000,
            stock_value=600_000,
            total_pnl=12_000,
            total_pnl_rate=0.8,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        self.calls.append(("holdings", ""))
        return [
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=2,
                avg_buy_price=70_000,
                current_price=71_000,
                pnl=2_000,
                pnl_rate=1.43,
            )
        ]

    async def get_volume_rank(self, market: str = "KRX") -> list[dict]:
        self.calls.append(("volume", market))
        return [
            {
                "symbol": "005930",
                "name": "삼성전자",
                "price": 71_000,
                "change_rate": 1.2,
                "volume": 123456,
            }
        ]

    async def get_fluctuation_rank(self, sort: str, market: str = "KRX") -> list[dict]:
        self.calls.append((sort, market))
        symbol = "035720" if sort == "top" else "000660"
        name = "카카오" if sort == "top" else "SK하이닉스"
        return [
            {
                "symbol": symbol,
                "name": name,
                "price": 52_000,
                "change_rate": 3.5 if sort == "top" else -2.1,
                "volume": 654321,
            }
        ]


@pytest.mark.asyncio
async def test_market_scanner_uses_broker_adapter_for_scan(monkeypatch) -> None:
    scanner = MarketScanner(broker_adapter=FakeScannerBrokerAdapter())
    logs = []
    decision_events = []
    captured_prompt: dict[str, str] = {}

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_event(**kwargs) -> None:
        decision_events.append(kwargs)

    async def fake_generate_tier1(*args, **kwargs) -> tuple[str, str]:
        captured_prompt["prompt"] = args[0]
        return (
            """
            {
              "selected": [
                {
                  "symbol": "005930",
                  "name": "삼성전자",
                  "strategy_type": "STABLE_SHORT",
                  "reason": "거래량 증가"
                }
              ],
              "market_analysis": "거래량이 유지되는 강세 흐름",
              "market_regime": "BULL"
            }
            """,
            "fake-provider",
        )

    async def fake_performance_summary() -> str:
        return "총 3거래, 승률 66.7%"

    async def fake_cooldown_symbols() -> set[str]:
        return set()

    async def fake_news_pressures(candidates) -> dict[str, float]:
        assert candidates
        return {"005930": 0.1}

    monkeypatch.setattr("agent.market_scanner.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.market_scanner.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr("agent.market_scanner.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(scanner, "_get_performance_summary", fake_performance_summary)
    monkeypatch.setattr(scanner, "_get_recent_candidate_cooldown_symbols", fake_cooldown_symbols)
    monkeypatch.setattr(scanner, "_get_candidate_news_pressures", fake_news_pressures)

    result = await scanner.scan(cycle_id="cycle-1")

    assert result["provider"] == "fake-provider"
    assert result["available_cash"] == 900_000
    assert result["selected"][0]["symbol"] == "005930"
    assert result["scored_candidates"][0]["symbol"] == "005930"
    assert "Deterministic 후보 점수" in captured_prompt["prompt"]
    assert "삼성전자(005930)" in captured_prompt["prompt"]
    assert "strategy=STABLE_SHORT" in captured_prompt["prompt"]
    assert "codes=HOLDING_REVIEW,VOLUME_RANK" in captured_prompt["prompt"]
    assert decision_events
    assert decision_events[0]["cycle_id"] == "cycle-1"
    assert decision_events[0]["decision_stage"] == "CANDIDATE_SCORING"
    assert decision_events[0]["source"] == "candidate_scoring"
    assert decision_events[0]["symbol"] == "005930"
    assert decision_events[0]["scanner_score"] == result["scored_candidates"][0]["score"]
    assert decision_events[0]["strategy_type"] == result["scored_candidates"][0]["strategy_type_hint"]
    assert decision_events[0]["final_action"] == "CANDIDATE"
    assert decision_events[0]["risk_gate_result"] == "PASS"
    assert decision_events[0]["metadata"]["rank"] == 1
    assert decision_events[0]["metadata"]["strategy_type_hint"] == "STABLE_SHORT"
    assert decision_events[0]["metadata"]["reason_codes"] == ["HOLDING_REVIEW", "VOLUME_RANK"]
    assert decision_events[0]["metadata"]["news_negative_pressure"] == 0.1
    assert logs
    assert scanner._broker_adapter.calls == [
        ("balance", ""),
        ("holdings", ""),
        ("volume", "KRX"),
        ("top", "KRX"),
        ("bottom", "KRX"),
    ]
