import pytest

from strategy.ai_risk_tuner import AIRiskTuner
from strategy.risk_manager import RiskManager
from strategy.signal import TradeSignal
from trading.enums import SignalAction


def test_ai_risk_tuner_normalizes_percent_cash_ratio_to_fraction() -> None:
    limits = AIRiskTuner()._clamp_limits({"min_cash_ratio": 30.0})

    assert limits["min_cash_ratio"] == pytest.approx(0.30)


@pytest.mark.asyncio
async def test_risk_manager_accepts_percent_style_dynamic_cash_ratio(monkeypatch) -> None:
    async def fake_log(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("strategy.risk_manager.activity_logger.log", fake_log)
    monkeypatch.setattr("strategy.risk_manager.settings.TRADING_ENABLED", True)

    manager = RiskManager()
    signal = TradeSignal(
        symbol="050890",
        stock_id="050890",
        action=SignalAction.BUY,
        strength=0.58,
        suggested_price=15_030,
        suggested_quantity=2_994,
        target_price=16_200,
        stop_loss_price=14_200,
    )

    result = await manager.check(
        signal=signal,
        portfolio_cash=500_000_000,
        portfolio_budget=500_000_000,
        today_trade_count=0,
        current_holding_count=0,
        dynamic_limits={
            "min_cash_ratio": 30.0,
            "min_buy_quantity": 1,
            "max_daily_trades": 15,
            "max_single_order_krw": 75_000_000,
            "max_position_pct": 15.0,
        },
        market_regime="BULL",
    )

    assert result["approved"] is True
    assert result["reason"] == "리스크 검사 통과"
