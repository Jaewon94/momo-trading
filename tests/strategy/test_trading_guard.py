import pytest

from strategy.trading_guard import TradingGuard


@pytest.mark.asyncio
async def test_trading_guard_blocks_buy_on_daily_drawdown(monkeypatch):
    guard = TradingGuard()

    async def fake_drawdown(*, portfolio_budget: float) -> float:
        return -3.2

    async def fake_losses() -> int:
        return 1

    async def fake_expectancy(strategy_type: str) -> float | None:
        return 0.1

    monkeypatch.setattr(guard, "_get_daily_realized_pnl_pct", fake_drawdown)
    monkeypatch.setattr(guard, "_get_consecutive_losses", fake_losses)
    monkeypatch.setattr(guard, "_get_strategy_expectancy", fake_expectancy)
    monkeypatch.setattr("strategy.trading_guard.settings.AUTO_RISK_KILL_SWITCH_ENABLED", True)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_DAILY_DRAWDOWN_PCT", 2.5)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_CONSECUTIVE_LOSSES", 4)
    monkeypatch.setattr("strategy.trading_guard.settings.MIN_STRATEGY_EXPECTANCY", 0.0)
    monkeypatch.setattr("strategy.trading_guard.settings.TRADING_ENABLED", True)

    result = await guard.evaluate_buy_guard(strategy_type="STABLE_SHORT", portfolio_budget=1_000_000)

    assert result["approved"] is False
    assert "일손실" in result["reason"]
    assert result["trigger"] == "DAILY_DRAWDOWN"
    assert result["kill_switched"] is True


@pytest.mark.asyncio
async def test_trading_guard_blocks_buy_on_negative_expectancy(monkeypatch):
    guard = TradingGuard()

    async def fake_drawdown(*, portfolio_budget: float) -> float:
        return -0.3

    async def fake_losses() -> int:
        return 0

    async def fake_expectancy(strategy_type: str) -> float | None:
        return -0.12

    monkeypatch.setattr(guard, "_get_daily_realized_pnl_pct", fake_drawdown)
    monkeypatch.setattr(guard, "_get_consecutive_losses", fake_losses)
    monkeypatch.setattr(guard, "_get_strategy_expectancy", fake_expectancy)
    monkeypatch.setattr("strategy.trading_guard.settings.AUTO_RISK_KILL_SWITCH_ENABLED", True)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_DAILY_DRAWDOWN_PCT", 2.5)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_CONSECUTIVE_LOSSES", 4)
    monkeypatch.setattr("strategy.trading_guard.settings.MIN_STRATEGY_EXPECTANCY", 0.0)
    monkeypatch.setattr("strategy.trading_guard.settings.TRADING_ENABLED", True)

    result = await guard.evaluate_buy_guard(strategy_type="AGGRESSIVE_SHORT", portfolio_budget=1_000_000)

    assert result["approved"] is False
    assert result["trigger"] == "NEGATIVE_EXPECTANCY"
    assert "기대값" in result["reason"]
