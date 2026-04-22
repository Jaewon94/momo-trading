from trading.account_manager import AccountManager
from trading.models import AccountBalance, HoldingInfo, PendingOrderInfo


class FakeBrokerAdapter:
    def __init__(self) -> None:
        self.balance_calls = 0
        self.holdings_calls = 0
        self.pending_order_calls = 0

    async def get_balance(self) -> AccountBalance:
        self.balance_calls += 1
        return AccountBalance(
            total_asset=500_000_000,
            cash=500_000_000,
            stock_value=0,
            total_pnl=0,
            total_pnl_rate=0,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        self.holdings_calls += 1
        return [
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=3,
                avg_buy_price=70_000,
                current_price=72_000,
                pnl=6_000,
                pnl_rate=2.86,
            )
        ]

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        self.pending_order_calls += 1
        return [
            PendingOrderInfo(
                order_id="1001",
                symbol="005930",
                name="삼성전자",
                side="매수",
                order_qty=3,
                filled_qty=0,
                remaining_qty=3,
                order_price=71_000,
                order_time="091500",
            )
        ]


async def test_account_manager_delegates_to_broker_adapter_for_non_kis(monkeypatch):
    adapter = FakeBrokerAdapter()
    manager = AccountManager()

    monkeypatch.setattr("trading.account_manager.settings.BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: adapter)
    monkeypatch.setattr("trading.account_manager.market_calendar.is_krx_trading_hours", lambda: True)

    balance, holdings = await manager.get_account_snapshot()
    orders = await manager.get_pending_orders()

    assert balance.total_asset == 500_000_000
    assert holdings[0].symbol == "005930"
    assert orders[0].order_id == "1001"
    assert adapter.balance_calls == 1
    assert adapter.holdings_calls == 1
    assert adapter.pending_order_calls == 1


async def test_account_manager_reuses_broker_cache_outside_trading_hours(monkeypatch):
    adapter = FakeBrokerAdapter()
    manager = AccountManager()

    monkeypatch.setattr("trading.account_manager.settings.BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: adapter)
    monkeypatch.setattr("trading.account_manager.market_calendar.is_krx_trading_hours", lambda: True)

    await manager.get_account_snapshot()
    await manager.get_pending_orders()

    monkeypatch.setattr("trading.account_manager.market_calendar.is_krx_trading_hours", lambda: False)

    balance, holdings = await manager.get_account_snapshot()
    orders = await manager.get_pending_orders()

    assert balance.total_asset == 500_000_000
    assert holdings[0].symbol == "005930"
    assert orders[0].order_id == "1001"
    assert adapter.balance_calls == 1
    assert adapter.holdings_calls == 1
    assert adapter.pending_order_calls == 1
