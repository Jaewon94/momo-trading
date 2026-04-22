import pytest

from agent.order_reservation import OrderReservationLedger
from agent.trading_agent import TradingAgent
from strategy.signal import TradeSignal
from trading.enums import SignalAction


def _buy_signal(symbol: str, *, price: float, quantity: int) -> TradeSignal:
    return TradeSignal(
        symbol=symbol,
        stock_id=symbol,
        action=SignalAction.BUY,
        strength=0.8,
        suggested_price=price,
        suggested_quantity=quantity,
    )


@pytest.mark.asyncio
async def test_trading_agent_blocks_second_buy_when_cycle_cash_is_reserved(monkeypatch):
    monkeypatch.setattr("agent.trading_agent.settings.ORDER_RESERVATION_ENFORCEMENT", "ENFORCE", raising=False)
    agent = TradingAgent(broker_adapter=None)
    ledger = OrderReservationLedger(starting_cash=100_000)

    first = await agent._reserve_buy_cash_for_cycle(_buy_signal("005930", price=10_000, quantity=7), ledger)
    second = await agent._reserve_buy_cash_for_cycle(_buy_signal("000660", price=10_000, quantity=4), ledger)

    assert first.approved is True
    assert second.approved is False
    assert second.reason == "예약 가능 현금 부족"
    assert ledger.available_cash == 30_000
