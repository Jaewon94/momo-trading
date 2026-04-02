from types import SimpleNamespace

import pytest

from scheduler.jobs.portfolio_sync_job import _recover_pending_confirms
from trading.enums import BrokerProvider, OrderConfirmStatus
from trading.models import HoldingInfo


@pytest.mark.asyncio
async def test_recover_pending_confirms_uses_kiwoom_holdings_for_filled_buy(monkeypatch) -> None:
    pending_trade = SimpleNamespace(
        order_id="0019412",
        stock_symbol="003280",
        side="BUY",
        quantity=7800,
        entry_price=1895.0,
        exit_price=0.0,
        notes="PENDING_CONFIRM",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return [pending_trade]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_pending_orders(self):
            return []

        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="003280",
                    name="흥아해운",
                    quantity=7800,
                    avg_buy_price=1895.0,
                    current_price=1910.0,
                    pnl=117000.0,
                    pnl_rate=0.79,
                )
            ]

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    await _recover_pending_confirms()

    assert pending_trade.status == OrderConfirmStatus.CONFIRMED.value
    assert pending_trade.quantity == 7800
    assert pending_trade.entry_price == 1895.0
    assert pending_trade.notes is None


@pytest.mark.asyncio
async def test_recover_pending_confirms_keeps_kiwoom_pending_when_unverifiable(monkeypatch) -> None:
    pending_trade = SimpleNamespace(
        order_id="0018385",
        stock_symbol="215790",
        side="BUY",
        quantity=22000,
        entry_price=671.0,
        exit_price=0.0,
        notes="PENDING_CONFIRM: 체결 확인 대기 중",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return [pending_trade]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_pending_orders(self):
            return []

        async def get_holdings(self):
            return []

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    await _recover_pending_confirms()

    assert pending_trade.status == OrderConfirmStatus.PENDING_CONFIRM.value
    assert pending_trade.notes == "PENDING_CONFIRM: 체결 확인 대기 중"
