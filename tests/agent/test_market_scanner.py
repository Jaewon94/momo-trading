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


class ProbationScannerBrokerAdapter(FakeScannerBrokerAdapter):
    async def get_balance(self) -> AccountBalance:
        self.calls.append(("balance", ""))
        return AccountBalance(
            total_asset=1_500_000,
            cash=900_000,
            stock_value=0,
            total_pnl=-80_000,
            total_pnl_rate=-5.1,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        self.calls.append(("holdings", ""))
        return []

    async def get_volume_rank(self, market: str = "KRX") -> list[dict]:
        self.calls.append(("volume", market))
        return [
            {
                "symbol": "011000",
                "name": "진원생명과학",
                "price": 1120,
                "change_rate": 21.2,
                "volume": 40000000,
            },
            {
                "symbol": "005930",
                "name": "삼성전자",
                "price": 71000,
                "change_rate": 5.2,
                "volume": 5000000,
            },
        ]

    async def get_fluctuation_rank(self, sort: str, market: str = "KRX") -> list[dict]:
        self.calls.append((sort, market))
        if sort == "top":
            return [
                {
                    "symbol": "011000",
                    "name": "진원생명과학",
                    "price": 1120,
                    "change_rate": 21.2,
                    "volume": 40000000,
                }
            ]
        return [
            {
                "symbol": "000660",
                "name": "SK하이닉스",
                "price": 180000,
                "change_rate": -2.1,
                "volume": 777777,
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

    async def fake_news_pressures(candidates, *, horizon=None) -> dict[str, float]:
        assert candidates
        assert horizon == "SHORT"
        return {"005930": 0.1}

    monkeypatch.setattr("agent.market_scanner.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.market_scanner.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr("agent.market_scanner.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(scanner, "_get_performance_summary", fake_performance_summary)
    monkeypatch.setattr(scanner, "_get_recent_candidate_cooldown_symbols", fake_cooldown_symbols)
    monkeypatch.setattr(scanner, "_get_candidate_news_pressures", fake_news_pressures)

    result = await scanner.scan(cycle_id="cycle-1")

    assert result["provider"] == "fake-provider"
    assert result["scan_horizon"] == "SHORT"
    assert result["available_cash"] == 900_000
    assert result["selected"][0]["symbol"] == "005930"
    assert result["selected"][0]["target_horizon_hint"] == "SHORT"
    assert result["selected"][0]["change_rate"] == 1.2
    assert result["selected"][0]["scanner_score"] == result["scored_candidates"][0]["score"]
    assert result["scored_candidates"][0]["symbol"] == "005930"
    assert [item["symbol"] for item in result["monitor_candidates"]] == ["005930", "035720", "000660"]
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


@pytest.mark.asyncio
async def test_market_scanner_filters_probation_overheat_and_adds_policy_candidate(monkeypatch) -> None:
    scanner = MarketScanner(broker_adapter=ProbationScannerBrokerAdapter())
    logs = []
    captured_prompt: dict[str, str] = {}

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_event(**kwargs) -> None:
        return None

    async def fake_generate_tier1(*args, **kwargs) -> tuple[str, str]:
        captured_prompt["prompt"] = args[0]
        return (
            """
            {
              "selected": [
                {
                  "symbol": "011000",
                  "name": "진원생명과학",
                  "strategy_type": "AGGRESSIVE_SHORT",
                  "reason": "급등 거래량",
                  "direction": "BUY"
                }
              ],
              "market_analysis": "급등주 중심의 과열 흐름",
              "market_regime": "THEME"
            }
            """,
            "fake-provider",
        )

    async def fake_performance_summary() -> str:
        return "총 5거래, 최근 5회 연속 손실"

    async def fake_cooldown_symbols() -> set[str]:
        return set()

    async def fake_news_pressures(candidates, *, horizon=None) -> dict[str, float]:
        return {}

    async def fake_consecutive_losses() -> int:
        return 5

    monkeypatch.setattr("agent.market_scanner.settings.MAX_CONSECUTIVE_LOSSES", 4)
    monkeypatch.setattr("agent.market_scanner.settings.LOSS_STREAK_RECOVERY_MODE", "PROBATION")
    monkeypatch.setattr("agent.market_scanner.settings.LOSS_STREAK_RECOVERY_MIN_CHANGE_PCT", 2.0)
    monkeypatch.setattr("agent.market_scanner.settings.LOSS_STREAK_RECOVERY_MAX_CHANGE_PCT", 10.0)
    monkeypatch.setattr("agent.market_scanner.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.market_scanner.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr("agent.market_scanner.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(scanner, "_get_performance_summary", fake_performance_summary)
    monkeypatch.setattr(scanner, "_get_recent_candidate_cooldown_symbols", fake_cooldown_symbols)
    monkeypatch.setattr(scanner, "_get_candidate_news_pressures", fake_news_pressures)
    monkeypatch.setattr(scanner, "_get_consecutive_losses", fake_consecutive_losses)

    result = await scanner.scan(cycle_id="cycle-probation")

    assert "BUY 후보 필수 조건: 전일대비 +2.00%~+10.00%" in captured_prompt["prompt"]
    assert [item["symbol"] for item in result["selected"]] == ["005930"]
    assert result["selected"][0]["strategy_type"] == "STABLE_SHORT"
    assert result["selected"][0]["target_horizon_hint"] == "SHORT"
    assert result["selected"][0]["strategy_alignment"] == "DETERMINISTIC_FALLBACK"
    assert result["scanner_policy"]["probation_active"] is True
    assert "011000" not in [item["symbol"] for item in result["selected"]]
    actions = [item["action"] for item in result["selection_policy_adjustments"]]
    assert "strategy_aligned" in actions
    assert "buy_filtered" in actions
    assert "buy_fallback_added" in actions
    overheat = next(item for item in result["scored_candidates"] if item["symbol"] == "011000")
    assert overheat["policy_buy_eligible"] is False
    assert "POLICY_CHANGE_OVER_MAX" in overheat["reason_codes"]


@pytest.mark.asyncio
async def test_market_scanner_mid_horizon_uses_mid_policy(monkeypatch) -> None:
    scanner = MarketScanner(broker_adapter=FakeScannerBrokerAdapter())
    captured_prompt: dict[str, str] = {}
    observed_news_horizon: list[str | None] = []

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_record_event(**kwargs) -> None:
        return None

    async def fake_generate_tier1(*args, **kwargs) -> tuple[str, str]:
        captured_prompt["prompt"] = args[0]
        return (
            """
            {
              "selected": [
                {
                  "symbol": "035720",
                  "name": "카카오",
                  "strategy_type": "STABLE_SHORT",
                  "reason": "중기 거래량 회복",
                  "direction": "BUY"
                }
              ],
              "market_analysis": "중기 회복 후보 중심",
              "market_regime": "SIDEWAYS"
            }
            """,
            "fake-provider",
        )

    async def fake_performance_summary() -> str:
        return "매매 이력 없음"

    async def fake_cooldown_symbols() -> set[str]:
        return set()

    async def fake_news_pressures(candidates, *, horizon=None) -> dict[str, float]:
        observed_news_horizon.append(horizon)
        return {}

    monkeypatch.setattr("agent.market_scanner.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.market_scanner.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr("agent.market_scanner.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(scanner, "_get_performance_summary", fake_performance_summary)
    monkeypatch.setattr(scanner, "_get_recent_candidate_cooldown_symbols", fake_cooldown_symbols)
    monkeypatch.setattr(scanner, "_get_candidate_news_pressures", fake_news_pressures)

    result = await scanner.scan(cycle_id="cycle-mid", horizon="MID")

    assert result["scan_horizon"] == "MID"
    assert result["scanner_policy"]["max_candidates"] == 60
    assert result["selected"][0]["target_horizon_hint"] == "MID"
    assert result["selected"][0]["scan_horizon"] == "MID"
    assert "스캔 호라이즌: MID" in captured_prompt["prompt"]
    assert observed_news_horizon == ["MID"]


def test_market_data_lookup_includes_raw_rank_rows() -> None:
    scanner = MarketScanner(broker_adapter=FakeScannerBrokerAdapter())

    lookup = scanner._build_market_data_lookup(
        [{"symbol": "005930", "price": 71_000, "change_rate": 1.2, "volume": 123456, "score": 61.5}],
        volume_rank=[{"symbol": "005930", "price": 70_900, "change_rate": 1.1, "volume": 120000}],
        surge_data=[{"symbol": "035720", "price": 52_000, "change_rate": 3.5, "volume": 654321}],
        drop_data=[{"symbol": "000660", "price": 180_000, "change_rate": -2.1, "volume": 777777}],
    )

    assert lookup["005930"]["change_rate"] == 1.2
    assert lookup["005930"]["scanner_score"] == 61.5
    assert lookup["035720"]["change_rate"] == 3.5
    assert lookup["035720"]["volume"] == 654321
    assert lookup["035720"]["scanner_sources"] == ["surge_data"]
    assert lookup["000660"]["change_rate"] == -2.1


def test_realtime_monitor_candidates_expand_beyond_selected() -> None:
    scanner = MarketScanner(broker_adapter=FakeScannerBrokerAdapter())

    candidates = scanner._build_realtime_monitor_candidates(
        selected=[{"symbol": "005930", "name": "삼성전자"}],
        scored_candidates=[{"symbol": "000660", "name": "SK하이닉스"}],
        volume_rank=[{"symbol": "035720", "name": "카카오", "price": 52_000}],
        surge_data=[{"symbol": "005930", "name": "삼성전자"}, {"symbol": "011930", "name": "신성이엔지"}],
        max_candidates=4,
    )

    assert [item["symbol"] for item in candidates] == ["005930", "000660", "035720", "011930"]
    assert all(item["market"] == "KRX" for item in candidates)
