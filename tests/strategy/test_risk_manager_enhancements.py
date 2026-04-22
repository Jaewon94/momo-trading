import pytest

from strategy.risk_manager import RiskManager
from strategy.signal import TradeSignal
from trading.enums import SignalAction


@pytest.mark.asyncio
async def test_risk_manager_adjusts_quantity_by_risk_budget(monkeypatch):
    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("strategy.risk_manager.activity_logger.log", fake_log)
    monkeypatch.setattr("strategy.risk_manager.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("strategy.risk_manager.settings.VOLATILITY_POSITION_SIZING_ENABLED", True)
    monkeypatch.setattr("strategy.risk_manager.settings.RISK_PER_TRADE_PCT", 0.5)

    manager = RiskManager()
    signal = TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.8,
        suggested_price=100.0,
        suggested_quantity=100,
        stop_loss_price=95.0,
    )

    result = await manager.check(
        signal=signal,
        portfolio_cash=100_000,
        portfolio_budget=10_000,
        today_trade_count=0,
        current_holding_count=0,
    )

    assert result["approved"] is True
    assert result["adjusted_quantity"] == 10
    assert "변동성" in result["reason"]


@pytest.mark.asyncio
async def test_risk_manager_applies_short_horizon_multiplier(monkeypatch):
    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("strategy.risk_manager.activity_logger.log", fake_log)
    monkeypatch.setattr("strategy.risk_manager.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("strategy.risk_manager.settings.VOLATILITY_POSITION_SIZING_ENABLED", True)
    monkeypatch.setattr("strategy.risk_manager.settings.RISK_PER_TRADE_PCT", 1.0)
    monkeypatch.setattr("strategy.risk_manager.settings.RISK_MULTIPLIER_SHORT", 0.5)
    monkeypatch.setattr("strategy.risk_manager.settings.RISK_MULTIPLIER_MID", 1.0)
    manager = RiskManager()

    signal = TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.8,
        suggested_price=100.0,
        suggested_quantity=100,
        stop_loss_price=95.0,
        metadata={"trade_horizon": "SHORT"},
    )

    result = await manager.check(
        signal=signal,
        portfolio_cash=100_000,
        portfolio_budget=10_000,
        today_trade_count=0,
        current_holding_count=0,
    )

    # risk_budget = 10_000 * 1.0% * 0.5 = 50, risk/share=5 => qty=10
    assert result["approved"] is True
    assert result["adjusted_quantity"] == 10


@pytest.mark.asyncio
async def test_risk_manager_blocks_buy_when_trading_guard_fails(monkeypatch):
    class FakeGuard:
        async def evaluate_buy_guard(self, strategy_type: str, portfolio_budget: float) -> dict:
            return {
                "approved": False,
                "reason": "자동 킬스위치: 연속 손실 4회",
                "trigger": "CONSECUTIVE_LOSSES",
                "kill_switched": True,
            }

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("strategy.risk_manager.activity_logger.log", fake_log)
    monkeypatch.setattr("strategy.risk_manager.settings.TRADING_ENABLED", True)
    manager = RiskManager(trading_guard=FakeGuard())
    signal = TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.8,
        suggested_price=100.0,
        suggested_quantity=10,
        strategy_type="STABLE_SHORT",
    )

    result = await manager.check(
        signal=signal,
        portfolio_cash=100_000,
        portfolio_budget=1_000_000,
        today_trade_count=0,
        current_holding_count=0,
    )

    assert result["approved"] is False
    assert result["trigger"] == "CONSECUTIVE_LOSSES"
