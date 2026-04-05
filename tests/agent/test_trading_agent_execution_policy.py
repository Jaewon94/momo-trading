from agent.trading_agent import TradingAgent
from strategy.signal import TradeSignal
from trading.enums import SignalAction


def _build_buy_signal(price: float | None) -> TradeSignal:
    return TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.8,
        suggested_price=price,
        suggested_quantity=10,
    )


def test_apply_buy_execution_policy_keeps_limit_when_guard_mode(monkeypatch):
    monkeypatch.setattr("agent.trading_agent.settings.BUY_ORDER_EXECUTION_MODE", "LIMIT_GUARD")
    monkeypatch.setattr("agent.trading_agent.settings.BUY_SLIPPAGE_GUARD_BPS", 25)

    signal = _build_buy_signal(price=71_000)
    TradingAgent._apply_buy_execution_policy(signal=signal, current_price=70_500)

    assert signal.suggested_price == 71_000


def test_apply_buy_execution_policy_builds_guard_limit_from_current_price(monkeypatch):
    monkeypatch.setattr("agent.trading_agent.settings.BUY_ORDER_EXECUTION_MODE", "LIMIT_GUARD")
    monkeypatch.setattr("agent.trading_agent.settings.BUY_SLIPPAGE_GUARD_BPS", 20)

    signal = _build_buy_signal(price=None)
    TradingAgent._apply_buy_execution_policy(signal=signal, current_price=50_000)

    assert signal.suggested_price == 50_100


def test_apply_buy_execution_policy_switches_to_market_mode(monkeypatch):
    monkeypatch.setattr("agent.trading_agent.settings.BUY_ORDER_EXECUTION_MODE", "MARKET")
    monkeypatch.setattr("agent.trading_agent.settings.BUY_SLIPPAGE_GUARD_BPS", 20)

    signal = _build_buy_signal(price=71_000)
    TradingAgent._apply_buy_execution_policy(signal=signal, current_price=70_000)

    assert signal.suggested_price is None
