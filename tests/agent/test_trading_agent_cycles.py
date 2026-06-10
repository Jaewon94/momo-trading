import asyncio
from datetime import datetime
import inspect
from types import SimpleNamespace

import pytest

from analysis.chart_analyzer import ChartAnalysisResult
from agent.trading_agent import TradingAgent
from core.events import Event, EventType
from services.tier1_analysis_cache_service import tier1_analysis_cache_service
from strategy.policy.trace import from_risk_result
from strategy.signal import TradeSignal
from trading.enums import SignalAction, SignalUrgency
from trading.models import BuyingPowerInfo


class StubBrokerAdapter:
    async def get_buying_power(self, symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=10, available_cash=1_000_000)


@pytest.fixture(autouse=True)
def _disable_fast_gate_by_default(monkeypatch):
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.DETERMINISTIC_TIER1_FAST_GATE_ENABLED",
        False,
        raising=False,
    )


def _kst_time(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 2, hour, minute, 0)


def test_analyze_and_trade_accepts_manual_model_override() -> None:
    params = inspect.signature(TradingAgent._analyze_and_trade).parameters
    assert "manual_model_override" in params


def test_apply_trade_thresholds_returns_active_risk_values(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    applied: dict[str, float] = {}

    def fake_set_thresholds(_symbol: str, **kwargs) -> None:
        applied.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.event_detector.set_thresholds", fake_set_thresholds)
    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "MODERATE")

    thresholds = agent._apply_trade_thresholds(
        "005930",
        {"target_price": 12_000, "stop_loss_price": 10_500, "trailing_stop_pct": 4.5},
        {"target_price": 12_500, "stop_loss_price": 10_000, "trailing_stop_pct": 4.0},
        current_price=11_000,
        horizon="SHORT",
    )

    assert thresholds == applied
    assert thresholds["take_profit"] == 12_500
    assert thresholds["stop_loss"] == 10_615
    assert thresholds["trailing_stop_pct"] == 4.0


def test_resolve_trade_thresholds_does_not_touch_event_detector(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())

    def fail_set_thresholds(*_args, **_kwargs) -> None:
        raise AssertionError("pure threshold resolver must not write to event detector")

    monkeypatch.setattr("agent.trading_agent.event_detector.set_thresholds", fail_set_thresholds)
    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "MODERATE")

    thresholds = agent._resolve_trade_thresholds(
        tier1={"target_price": 12_000, "stop_loss_price": 10_500},
        tier2={"target_price": 12_500, "stop_loss_price": 10_000},
        current_price=11_000,
        horizon="SHORT",
    )

    assert thresholds["take_profit"] == 12_500
    assert thresholds["stop_loss"] == 10_615
    assert thresholds["trailing_stop_pct"] == 0.8


@pytest.mark.asyncio
async def test_aggressive_exposure_alignment_raises_buy_quantity_and_logs(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    signal = TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.7,
        confidence=0.7,
        suggested_price=100_000,
        suggested_quantity=50,
        target_price=112_000,
        stop_loss_price=93_000,
        urgency=SignalUrgency.IMMEDIATE,
        strategy_type="AGGRESSIVE_SHORT",
        reason="test",
        metadata={"trade_horizon": "MID"},
    )

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "AGGRESSIVE")
    monkeypatch.setattr("agent.trading_agent.settings.AGGRESSIVE_EXPOSURE_ALIGNMENT_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.settings.AGGRESSIVE_TARGET_EXPOSURE_PCT", 25.0)
    monkeypatch.setattr("agent.trading_agent.settings.AGGRESSIVE_MIN_BUY_ORDER_KRW", 20_000_000)
    monkeypatch.setattr("agent.trading_agent.settings.AGGRESSIVE_EXPOSURE_MIN_CONFIDENCE", 0.65)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)

    decision = await agent._apply_aggressive_exposure_alignment(
        signal=signal,
        portfolio_snapshot={
            "cash": 400_000_000,
            "total_asset": 500_000_000,
            "stock_value": 25_000_000,
            "current_exposure_pct": 5.0,
        },
        dynamic_limits={"max_single_order_krw": 50_000_000, "max_position_pct": 15.0},
        market_regime="BULL",
        cycle_id="cycle-exposure",
        stock_name="삼성전자",
    )

    assert decision.applied is True
    assert signal.suggested_quantity == 50
    signal.suggested_quantity = decision.final_quantity
    assert signal.suggested_quantity == 200
    assert signal.metadata["exposure_alignment"]["applied"] is True
    assert signal.metadata["exposure_alignment"]["policy_trace"]["adjusted"] is True
    assert any("공격적 노출 보정" in args[2] for args, _kwargs in logs)
    assert logs[0][1]["detail"]["policy_trace"]["decisions"][0]["owner"] == "exposure_alignment"


@pytest.mark.asyncio
async def test_aggressive_exposure_alignment_does_not_raise_low_confidence(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    signal = TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.6,
        confidence=0.6,
        suggested_price=100_000,
        suggested_quantity=50,
        urgency=SignalUrgency.IMMEDIATE,
        strategy_type="AGGRESSIVE_SHORT",
        reason="test",
    )

    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "AGGRESSIVE")
    monkeypatch.setattr("agent.trading_agent.settings.AGGRESSIVE_EXPOSURE_MIN_CONFIDENCE", 0.65)

    decision = await agent._apply_aggressive_exposure_alignment(
        signal=signal,
        portfolio_snapshot={
            "cash": 400_000_000,
            "total_asset": 500_000_000,
            "stock_value": 25_000_000,
            "current_exposure_pct": 5.0,
        },
        dynamic_limits={"max_single_order_krw": 50_000_000, "max_position_pct": 15.0},
        market_regime="BULL",
        cycle_id="cycle-exposure",
        stock_name="삼성전자",
    )

    assert decision.applied is False
    assert decision.reason == "confidence_below_floor"
    assert signal.suggested_quantity == 50


def test_apply_trade_thresholds_widens_too_tight_stop_loss_by_risk_appetite(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    applied: dict[str, float] = {}

    def fake_set_thresholds(_symbol: str, **kwargs) -> None:
        applied.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.event_detector.set_thresholds", fake_set_thresholds)
    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "AGGRESSIVE")

    thresholds = agent._apply_trade_thresholds(
        "005930",
        {"target_price": 12_000, "stop_loss_price": 10_970},
        {},
        current_price=11_000,
        horizon="SHORT",
    )

    assert thresholds == applied
    assert thresholds["stop_loss"] == 10_670


def test_apply_trade_thresholds_preserves_tighter_existing_stop_for_holding(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    applied: dict[str, float] = {}

    def fake_set_thresholds(_symbol: str, **kwargs) -> None:
        applied.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.event_detector.set_thresholds", fake_set_thresholds)
    monkeypatch.setattr(
        "agent.trading_agent.event_detector.get_thresholds",
        lambda _symbol: SimpleNamespace(stop_loss=10_800),
    )
    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "MODERATE")

    thresholds = agent._apply_trade_thresholds(
        "005930",
        {"target_price": 12_000, "stop_loss_price": 10_000},
        {},
        current_price=11_000,
        horizon="SHORT",
        preserve_tighter_stop_loss=True,
    )

    assert thresholds == applied
    assert thresholds["stop_loss"] == 10_800


@pytest.mark.asyncio
async def test_take_profit_event_blocks_before_min_hold(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    agent._running = True
    logs: list[str] = []
    exit_calls: list[dict] = []

    async def fake_min_hold_reason(_symbol: str) -> str:
        return "MID 최소 보유 1440분 전 수익보호 매도 보류 (현재 20분)"

    async def fake_execute_exit_order(**kwargs):
        exit_calls.append(kwargs)
        return SimpleNamespace(success=True, message="ok")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr(agent, "_take_profit_min_hold_block_reason", fake_min_hold_reason)
    monkeypatch.setattr(agent, "_execute_exit_order", fake_execute_exit_order)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)

    await agent._on_take_profit(
        Event(
            type=EventType.TAKE_PROFIT_HIT,
            data={
                "symbol": "005930",
                "name": "삼성전자",
                "price": 73_000,
                "take_profit_price": 72_000,
            },
        )
    )

    assert exit_calls == []
    assert any("익절선 도달 보류" in message for message in logs)


@pytest.mark.asyncio
async def test_profit_guard_stop_event_blocks_before_min_hold(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    agent._running = True
    logs: list[str] = []
    exit_calls: list[dict] = []

    async def fake_min_hold_reason(_symbol: str, *, stop_loss_price: float, current_price: float) -> str:
        assert stop_loss_price == 2_037
        assert current_price == 2_010
        return "MID 최소 보유 1440분 전 수익보호 매도 보류 (현재 25분)"

    async def fake_execute_exit_order(**kwargs):
        exit_calls.append(kwargs)
        return SimpleNamespace(success=True, message="ok")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr(agent, "_stop_loss_min_hold_block_reason", fake_min_hold_reason)
    monkeypatch.setattr(agent, "_execute_exit_order", fake_execute_exit_order)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)

    await agent._on_stop_loss(
        Event(
            type=EventType.STOP_LOSS_HIT,
            data={
                "symbol": "459550",
                "name": "알트",
                "price": 2_010,
                "stop_loss_price": 2_037,
            },
        )
    )

    assert exit_calls == []
    assert any("손절 이벤트 보류" in message for message in logs)


@pytest.mark.asyncio
async def test_tight_loss_stop_event_blocks_before_soft_stop_min_hold(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    observed_at = datetime(2026, 6, 8, 10, 20)
    trade_result = SimpleNamespace(
        entry_price=10_000,
        strategy_type="STABLE_SHORT",
        notes='{"trade_horizon":"MID"}',
        entry_at=datetime(2026, 6, 8, 10, 0),
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            return trade_result

    monkeypatch.setattr("agent.trading_agent.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("util.time_util.now_kst", lambda: observed_at)
    monkeypatch.setattr("agent.trading_agent.settings.DEFAULT_STOP_LOSS_PCT_MID", -4.0)
    monkeypatch.setattr("agent.trading_agent.settings.MIN_HOLD_MINUTES_BEFORE_SOFT_STOP_EXIT_MID", 1440, raising=False)

    reason = await agent._stop_loss_min_hold_block_reason(
        "005930",
        stop_loss_price=9_900,
        current_price=9_750,
    )

    assert reason is not None
    assert "소프트 손절 보류" in reason
    assert "MID 최소 보유 1440분" in reason


@pytest.mark.asyncio
async def test_persist_open_position_thresholds_does_not_loosen_stop_loss(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    trade_result = SimpleNamespace(ai_stop_loss_price=10_800, ai_target_price=12_000)

    class FakeSession:
        def __init__(self) -> None:
            self.flushed = 0
            self.committed = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def flush(self) -> None:
            self.flushed += 1

        async def commit(self) -> None:
            self.committed += 1

    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            return trade_result

    monkeypatch.setattr("agent.trading_agent.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)

    protected = await agent._persist_open_position_thresholds(
        "005930",
        {"stop_loss": 10_000, "take_profit": 12_500},
    )

    assert protected == {"stop_loss": 10_800, "take_profit": 12_500}
    assert trade_result.ai_stop_loss_price == 10_800
    assert trade_result.ai_target_price == 12_500
    assert session.flushed == 1
    assert session.committed == 1


@pytest.mark.asyncio
async def test_persist_open_position_thresholds_blocks_profit_guard_stop_before_breakeven(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    trade_result = SimpleNamespace(
        entry_price=2_035,
        ai_stop_loss_price=1_972,
        ai_target_price=2_220,
        strategy_type="STABLE_SHORT",
        notes='{"trade_horizon":"MID","active_stop_loss":1972}',
    )

    class FakeSession:
        def __init__(self) -> None:
            self.flushed = 0
            self.committed = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def flush(self) -> None:
            self.flushed += 1

        async def commit(self) -> None:
            self.committed += 1

    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            return trade_result

    monkeypatch.setattr("agent.trading_agent.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.trading_agent.settings.BREAKEVEN_TRIGGER_PCT_MID", 1.5)

    protected = await agent._persist_open_position_thresholds(
        "459550",
        {"stop_loss": 2_037, "take_profit": 2_250},
        current_price=2_050,
        horizon="MID",
    )

    assert protected == {"stop_loss": 1_972, "take_profit": 2_250}
    assert trade_result.ai_stop_loss_price == 1_972
    assert trade_result.ai_target_price == 2_250
    assert session.flushed == 1
    assert session.committed == 1


@pytest.mark.asyncio
async def test_persist_open_position_thresholds_repairs_bad_profit_stop_from_notes(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    trade_result = SimpleNamespace(
        entry_price=2_035,
        ai_stop_loss_price=2_037,
        ai_target_price=2_220,
        strategy_type="STABLE_SHORT",
        notes='{"trade_horizon":"MID","active_stop_loss":1972}',
    )

    class FakeSession:
        def __init__(self) -> None:
            self.flushed = 0
            self.committed = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def flush(self) -> None:
            self.flushed += 1

        async def commit(self) -> None:
            self.committed += 1

    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            return trade_result

    monkeypatch.setattr("agent.trading_agent.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.trading_agent.settings.BREAKEVEN_TRIGGER_PCT_MID", 1.5)

    protected = await agent._persist_open_position_thresholds(
        "459550",
        {"stop_loss": 2_037, "take_profit": 2_250},
        current_price=2_050,
        horizon="MID",
    )

    assert protected["stop_loss"] == 1_972
    assert trade_result.ai_stop_loss_price == 1_972
    assert trade_result.ai_target_price == 2_250
    assert session.flushed == 1
    assert session.committed == 1


def test_apply_trade_thresholds_caps_mid_horizon_stop_loss_in_moderate_risk(monkeypatch) -> None:
    """MODERATE / MID 호라이즌은 최대 -8.0% 손실폭으로 캡되어야 한다."""
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    applied: dict[str, float] = {}

    def fake_set_thresholds(_symbol: str, **kwargs) -> None:
        applied.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.event_detector.set_thresholds", fake_set_thresholds)
    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "MODERATE")

    thresholds = agent._apply_trade_thresholds(
        "005930",
        # AI가 -10% 이상 stop을 줘도 -8.0%로 좁혀져야 한다.
        {"target_price": 14_500, "stop_loss_price": 11_800},
        {},
        current_price=13_220,
        horizon="MID",
    )

    assert thresholds == applied
    # 13220 * (1 - 0.08) = 12162.4
    assert abs(thresholds["stop_loss"] - 12_162.4) < 0.5


def test_apply_trade_thresholds_caps_long_horizon_stop_loss_in_conservative_risk(monkeypatch) -> None:
    """CONSERVATIVE / LONG 호라이즌은 최대 -10.0% 손실폭으로 캡되어야 한다."""
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    applied: dict[str, float] = {}

    def fake_set_thresholds(_symbol: str, **kwargs) -> None:
        applied.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.event_detector.set_thresholds", fake_set_thresholds)
    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "CONSERVATIVE")

    thresholds = agent._apply_trade_thresholds(
        "005930",
        # AI가 -12% stop을 줘도 -10.0%로 좁혀져야 한다.
        {"target_price": 220_000, "stop_loss_price": 176_000},
        {},
        current_price=200_000,
        horizon="LONG",
    )

    assert thresholds == applied
    # 200000 * (1 - 0.10) = 180000
    assert abs(thresholds["stop_loss"] - 180_000) < 1.0


def test_apply_scan_thresholds_clamps_sensitive_monitoring_values(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    applied: dict[str, dict] = {}

    def fake_set_thresholds(symbol: str, **kwargs) -> None:
        applied[symbol] = kwargs

    monkeypatch.setattr("agent.trading_agent.event_detector.set_thresholds", fake_set_thresholds)

    agent._apply_scan_thresholds([
        {
            "symbol": "005930",
            "monitoring": {
                "surge_pct": 5.0,
                "drop_pct": -5.0,
                "volume_spike_ratio": 3.0,
            },
        },
        {"symbol": "000660"},
    ])

    assert applied["005930"] == {
        "surge_pct": 2.5,
        "drop_pct": -2.5,
        "volume_spike_ratio": 1.5,
    }
    assert applied["000660"] == {
        "surge_pct": 2.5,
        "drop_pct": -2.5,
        "volume_spike_ratio": 1.5,
    }


def test_build_monitor_candidates_prefers_selected_then_expanded_scan_pool() -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())

    candidates = agent._build_monitor_candidates(
        {
            "monitor_candidates": [
                {"symbol": "005930", "name": "삼성전자"},
                {"symbol": "035720", "name": "카카오"},
            ],
            "scored_candidates": [{"symbol": "000660", "name": "SK하이닉스"}],
        },
        selected=[{"symbol": "005930", "name": "삼성전자", "market": "KRX"}],
    )

    assert [item["symbol"] for item in candidates] == ["005930", "035720", "000660"]
    assert agent._symbols_from_candidates(candidates) == [
        ("005930", "KRX"),
        ("035720", "KRX"),
        ("000660", "KRX"),
    ]


@pytest.mark.asyncio
async def test_run_cycle_skips_when_cycle_lock_is_held() -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    await agent._cycle_lock.acquire()

    try:
        result = await agent.run_cycle()
    finally:
        agent._cycle_lock.release()

    assert result == {"skipped": True, "reason": "cycle_already_running"}


@pytest.mark.asyncio
async def test_run_cycle_skips_new_buys_after_cutoff_in_day_trading_mode(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    activity_logs: list[tuple] = []

    async def fake_log(*args, **kwargs) -> None:
        activity_logs.append((args, kwargs))

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("agent.trading_agent.settings.BUY_CUTOFF_HOUR", 14)
    monkeypatch.setattr("agent.trading_agent.settings.BUY_CUTOFF_MINUTE", 30)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(14, 30))

    result = await agent.run_cycle()

    assert result == {"skipped": True, "reason": "buy_cutoff"}
    assert agent.last_cycle_time == _kst_time(14, 30)
    assert len(activity_logs) == 1


@pytest.mark.asyncio
async def test_run_cycle_skips_when_runtime_reconfiguration_is_active(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())

    monkeypatch.setattr(
        "agent.trading_agent.runtime_reconfiguration_service.is_reconfiguring",
        lambda: True,
    )

    result = await agent.run_cycle()

    assert result == {"skipped": True, "reason": "runtime_reconfiguring"}


@pytest.mark.asyncio
async def test_run_cycle_dispatches_trading_cycle_during_market_hours(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    observed: dict[str, str | None] = {}

    async def fake_trading_cycle(*, manual_provider_override: str | None = None, manual_model_override: str | None = None) -> dict:
        observed["manual_provider_override"] = manual_provider_override
        observed["manual_model_override"] = manual_model_override
        return {"mode": "trading"}

    async def fake_after_hours_cycle(*, manual_provider_override: str | None = None, manual_model_override: str | None = None) -> dict:
        raise AssertionError("after-hours cycle should not be called during market hours")

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr(agent, "_run_trading_cycle", fake_trading_cycle)
    monkeypatch.setattr(agent, "_run_after_hours_cycle", fake_after_hours_cycle)

    result = await agent.run_cycle(manual_provider_override="CODEX", manual_model_override="gpt-5.4")

    assert result == {"mode": "trading"}
    assert observed == {"manual_provider_override": "CODEX", "manual_model_override": "gpt-5.4"}


@pytest.mark.asyncio
async def test_run_cycle_dispatches_after_hours_cycle_outside_market_hours(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    observed: dict[str, str | None] = {}

    async def fake_trading_cycle(*, manual_provider_override: str | None = None, manual_model_override: str | None = None) -> dict:
        raise AssertionError("trading cycle should not be called outside market hours")

    async def fake_after_hours_cycle(*, manual_provider_override: str | None = None, manual_model_override: str | None = None) -> dict:
        observed["manual_provider_override"] = manual_provider_override
        observed["manual_model_override"] = manual_model_override
        return {"mode": "after-hours"}

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: False)
    monkeypatch.setattr(agent, "_run_trading_cycle", fake_trading_cycle)
    monkeypatch.setattr(agent, "_run_after_hours_cycle", fake_after_hours_cycle)

    result = await agent.run_cycle(manual_provider_override="CLAUDE_CODE", manual_model_override="claude-sonnet-4-6")

    assert result == {"mode": "after-hours"}
    assert observed == {"manual_provider_override": "CLAUDE_CODE", "manual_model_override": "claude-sonnet-4-6"}


@pytest.mark.asyncio
async def test_run_trading_cycle_returns_zeroed_results_when_snapshot_runtime_error(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    events = []
    logs = []

    async def fake_publish(event) -> None:
        events.append(event)

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_build_portfolio_snapshot() -> dict:
        raise RuntimeError("계좌 조회 실패")

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-1")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 5))

    result = await agent._run_trading_cycle()

    assert result == {
        "scan_horizon": "SHORT",
        "scan_horizon_label": "SHORT frequent",
        "scanned": 0,
        "analyzed": 0,
        "signals": 0,
        "executed": 0,
        "selected_symbols": [],
    }
    assert agent.last_cycle_time == _kst_time(9, 5)
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START]
    assert any("계좌 조회 실패" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_run_trading_cycle_completes_cleanly_when_scan_selects_no_candidates(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    events = []
    logs = []

    async def fake_publish(event) -> None:
        events.append(event)

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
        }

    async def fake_scan(*args, **kwargs) -> dict:
        assert kwargs.get("horizon") == "SHORT"
        return {"selected": []}

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-2")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 12)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 6))

    result = await agent._run_trading_cycle()

    assert result == {
        "scan_horizon": "SHORT",
        "scan_horizon_label": "SHORT frequent",
        "scanned": 0,
        "analyzed": 0,
        "signals": 0,
        "executed": 0,
        "selected_symbols": [],
    }
    assert agent.last_cycle_time == _kst_time(9, 6)
    assert agent._daily_start_balance == 2_000_000
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START]
    assert any("선정 종목 없음" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_run_trading_cycle_caches_scan_metadata_before_analysis(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    events = []
    logs = []
    applied_thresholds = []
    analyzed_payloads = []
    resume_calls = []

    async def fake_publish(event) -> None:
        events.append(event)

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {
            "selected": [{"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"}],
            "market_regime": "BULLISH",
        }

    async def fake_build_trading_context() -> str:
        return "trade-context"

    async def fake_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=10, available_cash=1_000_000)

    async def fake_analyze_and_trade(stock_info, cycle_id, **kwargs) -> dict:
        analyzed_payloads.append(
            {
                "stock_info": dict(stock_info),
                "cycle_id": cycle_id,
                "manual_provider_override": kwargs.get("manual_provider_override"),
                "manual_model_override": kwargs.get("manual_model_override"),
                "portfolio_snapshot": kwargs.get("portfolio_snapshot"),
            }
        )
        return {"signal": True, "executed": False}

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.pause_session", lambda: "session-1")
    monkeypatch.setattr("agent.trading_agent.llm_factory.resume_session", lambda sid: resume_calls.append(sid))
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: "ended-session")
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-3")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 50)
    monkeypatch.setattr("agent.trading_agent.settings.AI_RISK_TUNING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr(agent, "_build_market_context", lambda _scan_result: "market-context")
    monkeypatch.setattr(agent, "_build_trading_context", fake_build_trading_context)
    monkeypatch.setattr(agent, "_apply_scan_thresholds", lambda candidates: applied_thresholds.extend(dict(c) for c in candidates))
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fake_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 7))

    result = await agent._run_trading_cycle(manual_provider_override="CODEX", manual_model_override="gpt-5.4")

    assert result["scanned"] == 1
    assert result["analyzed"] == 1
    assert result["signals"] == 1
    assert result["executed"] == 0
    assert result["selected_symbols"] == [("005930", "KRX")]
    assert result["scan_horizon"] == "SHORT"
    assert agent._symbol_names == {"005930": "삼성전자"}
    assert agent._market_regime == "BULLISH"
    assert agent._market_context == "market-context"
    assert agent._trading_context == "trade-context"
    assert applied_thresholds == [{"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"}]
    assert analyzed_payloads[0]["manual_provider_override"] == "CODEX"
    assert analyzed_payloads[0]["manual_model_override"] == "gpt-5.4"
    assert analyzed_payloads[0]["portfolio_snapshot"]["total_asset"] == 2_000_000
    assert resume_calls == ["session-1"]
    assert agent._last_session_id == "ended-session"
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START, EventType.AGENT_CYCLE_END]
    assert any("사이클 완료" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_run_trading_cycle_respects_configured_analysis_concurrency(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    active = 0
    max_active = 0
    entered = 0
    first_entered = asyncio.Event()
    release = asyncio.Event()

    async def fake_publish(_event) -> None:
        return None

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {
            "selected": [
                {"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"},
                {"symbol": "000660", "name": "SK하이닉스", "market": "KRX", "direction": "BUY"},
                {"symbol": "035420", "name": "NAVER", "market": "KRX", "direction": "BUY"},
            ],
            "market_regime": "RANGE",
        }

    async def fake_build_trading_context() -> str:
        return "trade-context"

    async def fake_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=10, available_cash=1_000_000)

    async def fake_analyze_and_trade(*args, **kwargs) -> dict:
        nonlocal active, max_active, entered
        entered += 1
        active += 1
        max_active = max(max_active, active)
        if entered == 1:
            first_entered.set()
        await release.wait()
        active -= 1
        return {"signal": False, "executed": False}

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.pause_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: "session-end")
    monkeypatch.setattr("agent.trading_agent.llm_factory.analysis_concurrency_limit", lambda: 1)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-concurrency")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 20)
    monkeypatch.setattr("agent.trading_agent.settings.AI_RISK_TUNING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr(agent, "_build_market_context", lambda _scan_result: "market-context")
    monkeypatch.setattr(agent, "_build_trading_context", fake_build_trading_context)
    monkeypatch.setattr(agent, "_apply_scan_thresholds", lambda _candidates: None)
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fake_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 10))

    task = asyncio.create_task(agent._run_trading_cycle())
    await first_entered.wait()
    await asyncio.sleep(0.05)

    assert entered == 1
    assert max_active == 1

    release.set()
    result = await task

    assert result["scanned"] == 3
    assert result["analyzed"] == 3
    assert max_active == 1


@pytest.mark.asyncio
async def test_tier1_analysis_retries_once_when_first_response_is_unparseable(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    prompts = []
    responses = iter([
        ("not-json", "CODEX"),
        ('{"recommendation":"BUY","confidence":0.7,"reason":"ok","target_price":12000,"stop_loss_price":11000}', "CODEX"),
    ])
    parse_calls = []

    async def fake_generate_tier1(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(responses)

    def fake_parse_json(text: str):
        parse_calls.append(text)
        if text == "not-json":
            return None
        return {
            "recommendation": "BUY",
            "confidence": 0.7,
            "reason": "ok",
            "target_price": 12000,
            "stop_loss_price": 11000,
        }

    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(agent, "_parse_json", fake_parse_json)
    monkeypatch.setattr(agent, "_validate_llm_prices", lambda parsed, _price: parsed)

    result = await agent._tier1_analysis(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        chart_result=SimpleNamespace(indicators_text="", patterns_text="", trend_text=""),
        price_data={},
        deterministic_context="- deterministic_stage: TIER1_PRECHECK\n- chart_signal: BULLISH / confidence 70%",
    )

    assert result is not None
    assert result["recommendation"] == "BUY"
    assert result["provider"] == "CODEX"
    assert parse_calls == ["not-json", '{"recommendation":"BUY","confidence":0.7,"reason":"ok","target_price":12000,"stop_loss_price":11000}']
    assert "### Deterministic 사전 판단" in prompts[0]
    assert "deterministic_stage: TIER1_PRECHECK" in prompts[0]


@pytest.mark.asyncio
async def test_tier1_analysis_uses_manual_provider_override_when_present(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    captured = {}

    async def fake_generate_manual(*args, **kwargs):
        captured["provider_override"] = kwargs.get("manual_provider_override")
        captured["model_override"] = kwargs.get("manual_model_override")
        return '{"recommendation":"BUY","confidence":0.7,"reason":"ok","target_price":12000,"stop_loss_price":11000}', "CLAUDE_CODE"

    async def fail_generate_tier1(*args, **kwargs):
        raise AssertionError("generate_tier1 should not be used when manual override is provided")

    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_manual", fake_generate_manual)
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier1", fail_generate_tier1)
    monkeypatch.setattr(agent, "_parse_json", lambda _text: {
        "recommendation": "BUY",
        "confidence": 0.7,
        "reason": "ok",
        "target_price": 12000,
        "stop_loss_price": 11000,
    })
    monkeypatch.setattr(agent, "_validate_llm_prices", lambda parsed, _price: parsed)

    result = await agent._tier1_analysis(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        chart_result=SimpleNamespace(indicators_text="", patterns_text="", trend_text=""),
        price_data={},
        manual_provider_override="CLAUDE_CODE",
        manual_model_override="haiku",
    )

    assert result is not None
    assert result["provider"] == "CLAUDE_CODE"
    assert captured == {
        "provider_override": "CLAUDE_CODE",
        "model_override": "haiku",
    }


@pytest.mark.asyncio
async def test_tier1_analysis_timeout_returns_hold_fallback(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())

    async def slow_generate_tier1(*args, **kwargs):
        await asyncio.sleep(0.05)
        return '{"recommendation":"BUY","confidence":0.7,"reason":"late"}', "CODEX"

    monkeypatch.setattr("agent.trading_agent.settings.TIER1_LLM_TIMEOUT_SEC", 0.001, raising=False)
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier1", slow_generate_tier1)

    result = await agent._tier1_analysis(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        chart_result=SimpleNamespace(indicators_text="", patterns_text="", trend_text=""),
        price_data={},
    )

    assert result is not None
    assert result["recommendation"] == "HOLD"
    assert result["provider"] == "TIMEOUT_FALLBACK"
    assert "TIER1_LLM_TIMEOUT" in result["key_factors"]


def test_normalize_tier1_decision_preserves_position_management_exit_plan() -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())

    result = agent._normalize_tier1_decision(
        {
            "recommendation": "HOLD",
            "entry_action": "SKIP",
            "position_action": "TIGHTEN_STOP",
            "confidence": 0.62,
            "exit_plan": {
                "stop_loss_price": 10_800,
                "take_profit_price": 12_200,
                "trailing_stop_pct": 1.2,
            },
        },
        symbol="005930",
        portfolio_snapshot={"holding_symbols": ["005930"]},
    )

    assert result["recommendation"] == "HOLD"
    assert result["entry_action"] == "SKIP"
    assert result["position_action"] == "TIGHTEN_STOP"
    assert result["stop_loss_price"] == 10_800
    assert result["target_price"] == 12_200
    assert result["trailing_stop_pct"] == 1.2


@pytest.mark.asyncio
async def test_tier2_review_uses_tier_provider_without_manual_override(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    captured = {}

    async def fake_generate_tier2(prompt, *args, **kwargs):
        captured["prompt"] = prompt
        captured["symbol"] = kwargs.get("symbol")
        captured["cycle_id"] = kwargs.get("cycle_id")
        return '{"approved":true,"reason":"ok","suggested_quantity":10}', "CLAUDE_CODE"

    async def fail_generate_manual(*args, **kwargs):
        raise AssertionError("generate_manual should not be used without manual override")

    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier2", fake_generate_tier2)
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_manual", fail_generate_manual)
    monkeypatch.setattr(agent, "_parse_json", lambda _text: {
        "approved": True,
        "reason": "ok",
        "suggested_quantity": 10,
    })
    monkeypatch.setattr(agent, "_validate_llm_prices", lambda parsed, _price: parsed)

    result = await agent._tier2_review(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        strategy_type="STABLE_SHORT",
        tier1_analysis={"recommendation": "BUY"},
        cycle_id="cycle-tier2",
        deterministic_context="- deterministic_stage: TIER2_PRECHECK\n- code_rr_ratio: 2.00",
    )

    assert result is not None
    assert result["provider"] == "CLAUDE_CODE"
    assert captured["symbol"] == "005930"
    assert captured["cycle_id"] == "cycle-tier2"
    assert "### Deterministic 사전 판단" in captured["prompt"]
    assert "deterministic_stage: TIER2_PRECHECK" in captured["prompt"]


@pytest.mark.asyncio
async def test_tier2_review_uses_manual_provider_override_when_present(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    captured = {}

    async def fake_generate_manual(*args, **kwargs):
        captured["provider_override"] = kwargs.get("manual_provider_override")
        captured["model_override"] = kwargs.get("manual_model_override")
        return '{"approved":true,"reason":"ok","suggested_quantity":10}', "CODEX"

    async def fail_generate_tier2(*args, **kwargs):
        raise AssertionError("generate_tier2 should not be used when manual override is provided")

    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_manual", fake_generate_manual)
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier2", fail_generate_tier2)
    monkeypatch.setattr(agent, "_parse_json", lambda _text: {
        "approved": True,
        "reason": "ok",
        "suggested_quantity": 10,
    })
    monkeypatch.setattr(agent, "_validate_llm_prices", lambda parsed, _price: parsed)

    result = await agent._tier2_review(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        strategy_type="STABLE_SHORT",
        tier1_analysis={"recommendation": "BUY"},
        manual_provider_override="CODEX",
        manual_model_override="gpt-5-codex",
    )

    assert result is not None
    assert result["provider"] == "CODEX"
    assert captured == {
        "provider_override": "CODEX",
        "model_override": "gpt-5-codex",
    }


@pytest.mark.asyncio
async def test_analyze_and_trade_forwards_manual_model_override(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    forwarded: dict[str, str | None] = {}

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 70_000, "change": 0, "change_rate": 0, "volume": 1_000}, error=None)
        empty_resp = SimpleNamespace(success=False, data={}, error="no-data")
        return price_resp, empty_resp, empty_resp

    async def fake_tier1_analysis(*args, **kwargs) -> dict:
        forwarded["tier1_provider"] = kwargs.get("manual_provider_override")
        forwarded["tier1_model"] = kwargs.get("manual_model_override")
        return {
            "recommendation": "BUY",
            "confidence": 0.81,
            "reason": "테스트",
            "target_price": 72_000,
            "stop_loss_price": 68_000,
            "provider": "CODEX",
        }

    async def fake_tier2_review(*args, **kwargs) -> dict:
        forwarded["tier2_provider"] = kwargs.get("manual_provider_override")
        forwarded["tier2_model"] = kwargs.get("manual_model_override")
        return {"approved": False, "reason": "테스트", "provider": "CODEX"}

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr(agent, "_tier2_review", fake_tier2_review)

    result = await agent._analyze_and_trade(
        {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT"},
        "cycle-manual-model",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": ["005930"], "holding_count": 1, "today_trade_count": 0},
        manual_provider_override="CODEX",
        manual_model_override="gpt-5.4",
    )

    assert result == {"symbol": "005930", "signal": False, "executed": False}
    assert forwarded == {
        "tier1_provider": "CODEX",
        "tier1_model": "gpt-5.4",
        "tier2_provider": "CODEX",
        "tier2_model": "gpt-5.4",
    }


@pytest.mark.asyncio
async def test_run_trading_cycle_skips_buy_candidate_when_cash_is_blocked(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    analyze_called = False

    async def fake_publish(_event) -> None:
        return None

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 50_000,
            "total_asset": 1_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
            "min_holding_price": 100_000,
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {
            "selected": [{"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"}],
            "market_regime": "RANGE",
        }

    async def fake_build_trading_context() -> str:
        return "trade-context"

    async def fake_analyze_and_trade(*args, **kwargs) -> dict:
        nonlocal analyze_called
        analyze_called = True
        return {"executed": False}

    async def fail_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        raise AssertionError("buying power should not be checked when buy_blocked is true")

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.pause_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: "session-end")
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-cash-block")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 20)
    monkeypatch.setattr("agent.trading_agent.settings.AI_RISK_TUNING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr(agent, "_build_market_context", lambda _scan_result: "market-context")
    monkeypatch.setattr(agent, "_build_trading_context", fake_build_trading_context)
    monkeypatch.setattr(agent, "_apply_scan_thresholds", lambda _candidates: None)
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fail_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 8))

    result = await agent._run_trading_cycle()

    assert result["scanned"] == 1
    assert result["analyzed"] == 1
    assert result["signals"] == 0
    assert result["executed"] == 0
    assert result["selected_symbols"] == [("005930", "KRX")]
    assert analyze_called is False
    assert any("현금 부족" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_analyze_and_trade_skips_tier1_when_pre_analysis_gate_blocks_bearish_candidate(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    skipped_metrics = []
    decision_events = []

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_ai_skip(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_record_event(**kwargs):
        decision_events.append(kwargs)
        return SimpleNamespace(id="pre-analysis-event-1")

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 70_000}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 70_000, "high": 71_000, "low": 69_000, "close": 70_000, "volume": 1_000}]},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    def fake_chart_analyze(*args, **kwargs) -> ChartAnalysisResult:
        return ChartAnalysisResult(signal_summary={"direction": "BEARISH", "confidence": 0.8})

    async def fail_tier1_analysis(*args, **kwargs):
        raise AssertionError("Tier1 should not be called when PreAnalysisGate blocks the candidate")

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.ai_skip_metric_service.record", fake_record_ai_skip)
    monkeypatch.setattr("agent.trading_agent.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr("agent.trading_agent.chart_analyzer.analyze", fake_chart_analyze)
    monkeypatch.setattr(agent, "_tier1_analysis", fail_tier1_analysis)

    result = await agent._analyze_and_trade(
        {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT"},
        "cycle-pre-analysis-gate",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert result == {"symbol": "005930", "signal": False, "executed": False}
    assert any("사전 게이트 차단" in args[2] for args, _kwargs in logs)
    assert skipped_metrics == [
        {
            "stage": "PRE_ANALYSIS_GATE",
            "reason_code": "BEARISH_PRE_GATE",
            "skipped_tier": "TIER1",
            "cycle_id": "cycle-pre-analysis-gate",
            "symbol": "005930",
            "detail": {"direction": "BEARISH", "confidence": 0.8},
        }
    ]
    assert decision_events[0]["decision_stage"] == "PRE_ANALYSIS_GATE"
    assert decision_events[0]["source"] == "pre_analysis_gate"
    assert decision_events[0]["risk_gate_result"] == "BEARISH_PRE_GATE"
    assert decision_events[0]["final_action"] == "SKIP"
    assert decision_events[0]["reference_price"] == 70_000
    assert decision_events[0]["metadata"]["ai_skipped"] is True


@pytest.mark.asyncio
async def test_analyze_and_trade_skips_tier1_when_fast_gate_holds_candidate(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    skipped_metrics = []
    decision_events = []

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_ai_skip(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_record_event(**kwargs):
        decision_events.append(kwargs)
        return SimpleNamespace(id="fast-gate-event-1")

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 15_865, "change_rate": 28.0}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 15_000, "high": 16_000, "low": 14_800, "close": 15_865, "volume": 1_000}] * 6},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    def fake_chart_analyze(*args, **kwargs) -> ChartAnalysisResult:
        return ChartAnalysisResult(signal_summary={"direction": "NEUTRAL", "confidence": 0.1})

    def fake_fast_gate_evaluate(**kwargs):
        return SimpleNamespace(
            should_skip_tier1=True,
            code="FAST_GATE_HOLD",
            reason="late-day new buy cutoff",
            score=42.0,
            detail={"score": 42.0, "after_cutoff": True},
        )

    async def fail_tier1_analysis(*args, **kwargs):
        raise AssertionError("Tier1 should not be called when fast gate skips the candidate")

    monkeypatch.setattr("agent.trading_agent.settings.DETERMINISTIC_TIER1_FAST_GATE_MODE", "ENFORCE", raising=False)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.ai_skip_metric_service.record", fake_record_ai_skip)
    monkeypatch.setattr("agent.trading_agent.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr("agent.trading_agent.chart_analyzer.analyze", fake_chart_analyze)
    monkeypatch.setattr(
        "agent.trading_agent.deterministic_tier1_fast_gate_service.evaluate",
        fake_fast_gate_evaluate,
    )
    monkeypatch.setattr(agent, "_tier1_analysis", fail_tier1_analysis)

    result = await agent._analyze_and_trade(
        {"symbol": "006340", "name": "대원전선", "strategy_type": "AGGRESSIVE_SHORT"},
        "cycle-fast-gate",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert result == {"symbol": "006340", "signal": False, "executed": False}
    assert any("deterministic Tier1 fast gate" in args[2] for args, _kwargs in logs)
    assert skipped_metrics[0]["stage"] == "DETERMINISTIC_TIER1_FAST_GATE"
    assert skipped_metrics[0]["reason_code"] == "FAST_GATE_HOLD"
    assert decision_events[0]["decision_stage"] == "DETERMINISTIC_TIER1_FAST_GATE"
    assert decision_events[0]["final_action"] == "HOLD"


@pytest.mark.asyncio
async def test_analyze_and_trade_records_fast_gate_shadow_without_skipping_tier1(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    decision_events = []
    tier1_called = False

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_record_event(**kwargs):
        decision_events.append(kwargs)
        return SimpleNamespace(id="fast-gate-shadow-event-1")

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 15_865, "change_rate": 28.0}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 15_000, "high": 16_000, "low": 14_800, "close": 15_865, "volume": 1_000}] * 6},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    def fake_chart_analyze(*args, **kwargs) -> ChartAnalysisResult:
        return ChartAnalysisResult(signal_summary={"direction": "NEUTRAL", "confidence": 0.1})

    def fake_fast_gate_evaluate(**kwargs):
        assert kwargs["ignore_enabled"] is True
        return SimpleNamespace(
            action="HOLD",
            should_skip_tier1=True,
            code="FAST_GATE_HOLD",
            reason="late-day new buy cutoff",
            score=42.0,
            detail={"score": 42.0, "after_cutoff": True},
        )

    async def fake_tier1_analysis(*args, **kwargs):
        nonlocal tier1_called
        tier1_called = True
        return {
            "recommendation": "HOLD",
            "confidence": 0.2,
            "reason": "Tier1 still ran in shadow mode",
            "provider": "TEST",
        }

    monkeypatch.setattr("agent.trading_agent.settings.DETERMINISTIC_TIER1_FAST_GATE_MODE", "SHADOW", raising=False)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr("agent.trading_agent.chart_analyzer.analyze", fake_chart_analyze)
    monkeypatch.setattr(
        "agent.trading_agent.deterministic_tier1_fast_gate_service.evaluate",
        fake_fast_gate_evaluate,
    )
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr("agent.trading_agent.tier1_analysis_cache_service.get", lambda _key: None)
    monkeypatch.setattr("agent.trading_agent.tier1_analysis_cache_service.put", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "agent.trading_agent.deterministic_prompt_context_service.build_tier1_context",
        lambda **_kwargs: "deterministic context",
    )
    monkeypatch.setattr(
        "agent.trading_agent.news_context_service.build_for_symbol",
        lambda *_args, **_kwargs: asyncio.sleep(0, result={"prompt": "news context"}),
    )

    result = await agent._analyze_and_trade(
        {"symbol": "006340", "name": "대원전선", "strategy_type": "AGGRESSIVE_SHORT"},
        "cycle-fast-gate-shadow",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert result == {"symbol": "006340", "signal": False, "executed": False}
    assert tier1_called is True
    assert decision_events[0]["decision_stage"] == "DETERMINISTIC_TIER1_FAST_GATE_SHADOW"
    assert decision_events[0]["source"] == "deterministic_tier1_fast_gate"
    assert decision_events[0]["risk_gate_result"] == "FAST_GATE_HOLD"
    assert decision_events[0]["final_action"] == "SHADOW_HOLD"
    assert decision_events[0]["metadata"]["ai_shadow"] is True
    assert decision_events[0]["metadata"]["would_skip_tier1"] is True


@pytest.mark.asyncio
async def test_analyze_and_trade_skips_tier2_when_deterministic_final_gate_blocks_low_confidence(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    skipped_metrics = []
    decision_events = []
    agent._active_trading_rules = {"param_overrides": {"ALL": {"min_confidence": 0.7}}}
    agent._market_regime = "SIDEWAYS"

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_ai_skip(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_record_event(**kwargs):
        decision_events.append(kwargs)
        return SimpleNamespace(id="final-gate-event-1")

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 70_000}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 70_000, "high": 71_000, "low": 69_000, "close": 70_000, "volume": 1_000}]},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    async def fake_tier1_analysis(*args, **kwargs) -> dict:
        return {
            "recommendation": "BUY",
            "confidence": 0.6,
            "reason": "테스트",
            "target_price": 72_000,
            "stop_loss_price": 68_000,
            "provider": "CODEX",
        }

    async def fail_tier2_review(*args, **kwargs):
        raise AssertionError("Tier2 should not be called when DeterministicFinalGate blocks the candidate")

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.ai_skip_metric_service.record", fake_record_ai_skip)
    monkeypatch.setattr("agent.trading_agent.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr(agent, "_tier2_review", fail_tier2_review)

    result = await agent._analyze_and_trade(
        {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT", "_buying_power": {"success": True, "max_qty": 10}},
        "cycle-deterministic-final-gate",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert result == {"symbol": "005930", "signal": False, "executed": False}
    assert any("신뢰도 게이트 차단" in args[2] for args, _kwargs in logs)
    assert skipped_metrics
    assert skipped_metrics[0]["stage"] == "DETERMINISTIC_FINAL_GATE"
    assert skipped_metrics[0]["reason_code"] == "CONFIDENCE_GATE"
    assert skipped_metrics[0]["skipped_tier"] == "TIER2"
    assert decision_events[0]["decision_stage"] == "DETERMINISTIC_FINAL_GATE"
    assert decision_events[0]["source"] == "deterministic_final_gate"
    assert decision_events[0]["risk_gate_result"] == "CONFIDENCE_GATE"
    assert decision_events[0]["tier1_decision"] == "BUY"
    assert decision_events[0]["final_action"] == "SKIP"
    assert decision_events[0]["confidence"] == 0.6


@pytest.mark.asyncio
async def test_analyze_and_trade_skips_tier2_when_tier1_cost_gate_blocks_low_edge(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    skipped_metrics = []
    decision_events = []

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_ai_skip(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_record_event(**kwargs):
        decision_events.append(kwargs)
        return SimpleNamespace(id="cost-gate-event-1")

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 100.0, "change_rate": 0.0}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1_000}]},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    async def fake_tier1_analysis(*args, **kwargs) -> dict:
        return {
            "recommendation": "BUY",
            "confidence": 0.9,
            "reason": "edge too small",
            "target_price": 100.3,
            "stop_loss_price": 99.0,
            "provider": "CODEX",
        }

    async def fail_tier2_review(*args, **kwargs):
        raise AssertionError("Tier2 should not be called when Tier1 cost gate blocks the candidate")

    monkeypatch.setattr("agent.trading_agent.settings.COST_GATE_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_ENTRY_COST_BPS", 8)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_EXIT_COST_BPS", 8)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_SLIPPAGE_BPS_SHORT", 12)
    monkeypatch.setattr("agent.trading_agent.settings.MIN_EDGE_TO_COST_RATIO_SHORT", 1.5)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.ai_skip_metric_service.record", fake_record_ai_skip)
    monkeypatch.setattr("agent.trading_agent.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr(agent, "_tier2_review", fail_tier2_review)

    result = await agent._analyze_and_trade(
        {"symbol": "005930", "name": "삼성전자", "strategy_type": "AGGRESSIVE_SHORT", "_buying_power": {"success": True, "max_qty": 10}},
        "cycle-tier1-cost-gate",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert result == {"symbol": "005930", "signal": False, "executed": False}
    assert any("비용 게이트 사전 차단" in args[2] for args, _kwargs in logs)
    assert skipped_metrics[0]["stage"] == "TIER1_COST_GATE"
    assert decision_events[0]["decision_stage"] == "TIER1_COST_GATE"
    assert decision_events[0]["source"] == "tier1_cost_gate"
    assert decision_events[0]["risk_gate_result"] == "LOW_EDGE_AFTER_COST"
    assert decision_events[0]["tier1_decision"] == "BUY"


@pytest.mark.asyncio
async def test_analyze_and_trade_enforces_risk_adjusted_quantity_before_order(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    observed: dict = {}

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 100.0, "change_rate": 0.0}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1_000}]},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    async def fake_tier1_analysis(*args, **kwargs) -> dict:
        return {
            "recommendation": "BUY",
            "confidence": 0.9,
            "reason": "테스트",
            "target_price": 120.0,
            "stop_loss_price": 90.0,
            "provider": "CODEX",
        }

    async def fake_tier2_review(*args, **kwargs) -> dict:
        return {
            "approved": True,
            "action": "BUY",
            "reason": "테스트 승인",
            "suggested_quantity": 500,
            "entry_price": 100.0,
            "target_price": 120.0,
            "stop_loss_price": 90.0,
            "provider": "CODEX",
        }

    async def fake_risk_manager(**kwargs):
        assert kwargs["signal"].suggested_quantity == 500
        result = {
            "approved": True,
            "reason": "수량 조정 (테스트): 500 → 50",
            "adjusted_quantity": 50,
            "previous_quantity": 500,
            "adjustments": [
                {
                    "stage": "TEST_PARITY_CAP",
                    "previous_quantity": 500,
                    "adjusted_quantity": 50,
                    "reason": "테스트 수량 제한",
                }
            ],
        }
        return SimpleNamespace(
            value=result,
            decision=from_risk_result(result, input_quantity=kwargs.get("input_quantity")),
        )

    async def fake_news_gate(**kwargs):
        return SimpleNamespace(value={"approved": True, "reason": "뉴스 게이트 통과"}, decision=None)

    async def fake_execute(signal, cycle_id=None, analysis_context=None):
        observed["quantity"] = signal.suggested_quantity
        observed["cycle_id"] = cycle_id
        observed["analysis_context"] = analysis_context
        return {"success": True}

    async def fake_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=1_000, available_cash=1_000_000)

    monkeypatch.setattr("agent.trading_agent.settings.COST_GATE_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.settings.RISK_APPETITE", "MODERATE")
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr(agent, "_tier2_review", fake_tier2_review)
    monkeypatch.setattr(agent, "_apply_trade_thresholds", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(agent.policy_engine, "evaluate_risk_manager", fake_risk_manager)
    monkeypatch.setattr(agent.policy_engine, "evaluate_news_gate", fake_news_gate)
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fake_buying_power)
    monkeypatch.setattr("agent.trading_agent.decision_maker.execute", fake_execute)
    monkeypatch.setattr("agent.trading_agent.tier1_analysis_cache_service.get", lambda _key: None)
    monkeypatch.setattr("agent.trading_agent.tier1_analysis_cache_service.put", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "agent.trading_agent.deterministic_prompt_context_service.build_tier1_context",
        lambda **_kwargs: "deterministic context",
    )
    monkeypatch.setattr(
        "agent.trading_agent.deterministic_prompt_context_service.build_tier2_context",
        lambda **_kwargs: "deterministic tier2 context",
    )
    monkeypatch.setattr(
        "agent.trading_agent.news_context_service.build_for_symbol",
        lambda *_args, **_kwargs: asyncio.sleep(0, result={"available": False, "prompt": "news context"}),
    )

    result = await agent._analyze_and_trade(
        {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT"},
        "cycle-risk-adjustment-parity",
        portfolio_snapshot={
            "cash": 1_000_000,
            "total_asset": 1_000_000,
            "holding_symbols": [],
            "holding_count": 0,
            "today_trade_count": 0,
        },
        dynamic_limits={"min_buy_quantity": 1, "max_single_order_krw": 100_000_000},
    )

    assert result["signal"] is True
    assert result["executed"] is True
    assert observed["quantity"] == 50
    assert observed["cycle_id"] == "cycle-risk-adjustment-parity"


@pytest.mark.asyncio
async def test_analyze_and_trade_reuses_tier1_cache_for_same_symbol_conditions(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    skipped_metrics = []
    tier1_calls = 0
    tier1_analysis_cache_service.clear()

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_ai_skip(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 70_000}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 70_000, "high": 71_000, "low": 69_000, "close": 70_000, "volume": 1_000}]},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    async def fake_tier1_analysis(*args, **kwargs) -> dict:
        nonlocal tier1_calls
        tier1_calls += 1
        return {
            "recommendation": "HOLD",
            "confidence": 0.65,
            "reason": "테스트 캐시",
            "provider": "CODEX",
        }

    async def fail_tier2_review(*args, **kwargs):
        raise AssertionError("Tier2 should not be called for HOLD")

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.ai_skip_metric_service.record", fake_record_ai_skip)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr(agent, "_tier2_review", fail_tier2_review)

    payload = {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT"}
    snapshot = {"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0}

    first = await agent._analyze_and_trade(payload, "cycle-tier1-cache-1", portfolio_snapshot=snapshot)
    second = await agent._analyze_and_trade(payload, "cycle-tier1-cache-2", portfolio_snapshot=snapshot)

    assert first == {"symbol": "005930", "signal": False, "executed": False}
    assert second == {"symbol": "005930", "signal": False, "executed": False}
    assert tier1_calls == 1
    assert any("Tier1 캐시 재사용" in args[2] for args, _kwargs in logs)
    assert any(item["stage"] == "TIER1_CACHE" and item["reason_code"] == "CACHE_HIT" for item in skipped_metrics)


@pytest.mark.asyncio
async def test_run_trading_cycle_skips_buy_candidate_when_buying_power_is_too_low(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    analyze_called = False

    async def fake_publish(_event) -> None:
        return None

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 1_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
            "min_holding_price": 0,
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {
            "selected": [{"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"}],
            "market_regime": "RANGE",
        }

    async def fake_build_trading_context() -> str:
        return "trade-context"

    async def fake_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=0, available_cash=0)

    async def fake_analyze_and_trade(*args, **kwargs) -> dict:
        nonlocal analyze_called
        analyze_called = True
        return {"executed": False}

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.pause_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: "session-end")
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-buying-power")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 20)
    monkeypatch.setattr("agent.trading_agent.settings.AI_RISK_TUNING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr(agent, "_build_market_context", lambda _scan_result: "market-context")
    monkeypatch.setattr(agent, "_build_trading_context", fake_build_trading_context)
    monkeypatch.setattr(agent, "_apply_scan_thresholds", lambda _candidates: None)
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fake_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 9))

    result = await agent._run_trading_cycle()

    assert result["scanned"] == 1
    assert result["analyzed"] == 1
    assert result["signals"] == 0
    assert result["executed"] == 0
    assert analyze_called is False


@pytest.mark.asyncio
async def test_on_market_event_normalizes_a_prefixed_symbol_before_analysis(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    agent._running = True
    observed: dict = {}
    logged: list[tuple] = []

    async def fake_log(*args, **kwargs) -> None:
        logged.append((args, kwargs))

    async def fake_trading_context() -> str:
        return "live-context"

    async def fake_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 1,
            "today_trade_count": 0,
            "holding_symbols": ["010170"],
        }

    async def fake_analyze_and_trade(stock_info, cycle_id, **kwargs) -> dict:
        observed["stock_info"] = dict(stock_info)
        observed["cycle_id"] = cycle_id
        observed["portfolio_snapshot"] = kwargs.get("portfolio_snapshot")
        return {"executed": False}

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-live")
    monkeypatch.setattr(agent, "_build_trading_context", fake_trading_context)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_snapshot)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)

    await agent._on_market_event(Event(
        type=EventType.PRICE_SURGE,
        data={
            "symbol": "A010170",
            "name": "대한광통신",
            "price": 10_030,
            "change_rate": 6.59,
        },
        source="test",
    ))

    assert observed["stock_info"]["symbol"] == "010170"
    assert observed["stock_info"]["name"] == "대한광통신"
    assert observed["portfolio_snapshot"]["holding_symbols"] == ["010170"]
    assert logged[0][1]["symbol"] == "010170"


@pytest.mark.asyncio
async def test_on_market_event_skips_analysis_when_trading_disabled(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    agent._running = True
    called = False

    async def fake_analyze_and_trade(*args, **kwargs) -> dict:
        nonlocal called
        called = True
        return {"executed": False}

    monkeypatch.setattr("agent.trading_agent.settings.TRADING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)

    await agent._on_market_event(Event(
        type=EventType.PRICE_SURGE,
        data={
            "symbol": "A010170",
            "name": "대한광통신",
            "price": 10_030,
            "change_rate": 6.59,
        },
        source="test",
    ))

    assert called is False


@pytest.mark.asyncio
async def test_run_after_hours_cycle_generates_review_and_saves_report(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    events = []
    logs = []
    saved_reports = []
    generate_manual_calls = []
    end_session_calls = []

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeActivityRepo:
        def __init__(self, _session) -> None:
            pass

        async def count_by_date(self, _date):
            return {"CYCLE": 4, "TIER1_ANALYSIS": 3, "DECISION": 2, "ORDER": 1}

        async def get_by_date(self, _date, limit=50):
            return [SimpleNamespace(activity_type="CYCLE", phase="COMPLETE", summary="사이클 종료")]

    class FakePerformanceTracker:
        def __init__(self, _session) -> None:
            pass

        async def get_overall_stats(self):
            return {"overall": SimpleNamespace(total_trades=5, win_rate=0.6, total_pnl=12_345)}

    async def fake_publish(event) -> None:
        events.append(event)

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_collect_market_close_data():
        return ("close-data", "volume-data", "surge-data", "drop-data")

    async def fake_get_balance():
        return SimpleNamespace(
            total_asset=2_000_000,
            cash=1_000_000,
            stock_value=1_000_000,
            total_pnl=50_000,
            total_pnl_rate=2.5,
        )

    async def fake_generate_manual(prompt, **kwargs):
        generate_manual_calls.append({"prompt": prompt, **kwargs})
        return ('{"today_review":"좋음"}', "CODEX")

    async def fake_save_daily_report(report_date, parsed, **kwargs):
        saved_reports.append((report_date, parsed, kwargs))

    async def fake_generate_rules_from_review(parsed, today_date):
        return []

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: end_session_calls.append("end") or "after-hours-session")
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_manual", fake_generate_manual)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-after-hours")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 80)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.agent_activity_repository.AgentActivityRepository", FakeActivityRepo)
    monkeypatch.setattr("analysis.feedback.performance_tracker.PerformanceTracker", FakePerformanceTracker)
    monkeypatch.setattr("analysis.feedback.trading_rules.trading_rule_engine.generate_rules_from_review", fake_generate_rules_from_review)
    monkeypatch.setattr(agent, "_collect_market_close_data", fake_collect_market_close_data)
    monkeypatch.setattr(agent, "_save_daily_report", fake_save_daily_report)
    monkeypatch.setattr(agent, "_parse_json", lambda _text: {"today_review": "좋음", "trade_evaluation": {"total_trades": 1}})
    monkeypatch.setattr(agent, "_broker_adapter", SimpleNamespace(get_balance=fake_get_balance))
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("agent.trading_agent.market_calendar.next_krx_open", lambda: _kst_time(9, 0))
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(16, 0))

    result = await agent._run_after_hours_cycle(manual_provider_override="CODEX", manual_model_override="gpt-5.4")

    assert result == {"mode": "AFTER_HOURS", "review_generated": True}
    assert generate_manual_calls[0]["manual_provider_override"] == "CODEX"
    assert generate_manual_calls[0]["manual_model_override"] == "gpt-5.4"
    assert saved_reports and saved_reports[0][1]["today_review"] == "좋음"
    assert end_session_calls == ["end"]
    assert agent._last_session_id is None
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START, EventType.AGENT_CYCLE_END]
    assert any("장 마감 리뷰 완료" in args[2] for args, _kwargs in logs)
