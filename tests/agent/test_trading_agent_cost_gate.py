from agent.trading_agent import TradingAgent
from strategy.signal import TradeSignal
from trading.enums import SignalAction


def _buy_signal(entry: float, target: float) -> TradeSignal:
    return TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.8,
        suggested_price=entry,
        suggested_quantity=10,
        target_price=target,
    )


def test_cost_gate_blocks_when_edge_too_small(monkeypatch):
    monkeypatch.setattr("agent.trading_agent.settings.COST_GATE_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_ENTRY_COST_BPS", 8)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_EXIT_COST_BPS", 8)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_SLIPPAGE_BPS_SHORT", 12)
    monkeypatch.setattr("agent.trading_agent.settings.MIN_EDGE_TO_COST_RATIO_SHORT", 1.5)

    result = TradingAgent._evaluate_cost_gate(
        signal=_buy_signal(100.0, 100.3),  # edge 30bp
        current_price=100.0,
        horizon="SHORT",
    )

    assert result["approved"] is False
    assert result["cost_bps"] == 28


def test_cost_gate_passes_when_edge_large_enough(monkeypatch):
    monkeypatch.setattr("agent.trading_agent.settings.COST_GATE_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_ENTRY_COST_BPS", 8)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_EXIT_COST_BPS", 8)
    monkeypatch.setattr("agent.trading_agent.settings.ESTIMATED_SLIPPAGE_BPS_MID", 8)
    monkeypatch.setattr("agent.trading_agent.settings.MIN_EDGE_TO_COST_RATIO_MID", 1.3)

    result = TradingAgent._evaluate_cost_gate(
        signal=_buy_signal(100.0, 101.0),  # edge 100bp
        current_price=100.0,
        horizon="MID",
    )

    assert result["approved"] is True
