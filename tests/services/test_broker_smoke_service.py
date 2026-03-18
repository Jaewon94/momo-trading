from datetime import datetime

import pytest

from services.broker_smoke_service import run_broker_smoke_test
from trading.enums import BrokerProvider, Market
from trading.models import AccountBalance, BrokerCapabilities, CurrentPrice, HoldingInfo, PendingOrderInfo


class FakeBrokerAdapter:
    provider = BrokerProvider.KIWOOM
    capabilities = BrokerCapabilities(
        supports_domestic_stocks=True,
        supports_overseas_stocks=False,
        supports_paper_trading=True,
        supports_live_trading=True,
        supports_realtime_quotes=True,
        supports_order_cancellation=False,
    )

    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_asset=1_500_000,
            cash=900_000,
            stock_value=600_000,
            total_pnl=10_000,
            total_pnl_rate=0.67,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        return [
            HoldingInfo(
                symbol="005930",
                name="Samsung Electronics",
                quantity=2,
                avg_buy_price=70_000,
                current_price=71_000,
                pnl=2_000,
                pnl_rate=1.43,
            )
        ]

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return [
            PendingOrderInfo(
                order_id="1001",
                symbol="005930",
                name="Samsung Electronics",
                side="BUY",
                order_qty=2,
                filled_qty=0,
                remaining_qty=2,
                order_price=70_500,
                order_time="091500",
            )
        ]

    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        return CurrentPrice(
            symbol=symbol,
            market=market,
            price=71_000,
            change=500,
            change_rate=0.71,
            volume=123456,
            timestamp=datetime(2026, 3, 18, 9, 5, 0),
        )


class QuoteFailureBrokerAdapter(FakeBrokerAdapter):
    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        raise RuntimeError("quote unavailable")


@pytest.mark.asyncio
async def test_run_broker_smoke_test_collects_read_only_checks() -> None:
    result = await run_broker_smoke_test(
        adapter=FakeBrokerAdapter(),
        symbol="005930",
        market=Market.KRX,
    )

    assert result["ok"] is True
    assert result["provider"] == "KIWOOM"
    assert result["symbol"] == "005930"
    assert result["checks"]["balance"]["ok"] is True
    assert result["checks"]["holdings"]["count"] == 1
    assert result["checks"]["pending_orders"]["count"] == 1
    assert result["checks"]["quote"]["price"] == 71_000


@pytest.mark.asyncio
async def test_run_broker_smoke_test_reports_partial_failure() -> None:
    result = await run_broker_smoke_test(
        adapter=QuoteFailureBrokerAdapter(),
        symbol="005930",
        market=Market.KRX,
    )

    assert result["ok"] is False
    assert result["checks"]["balance"]["ok"] is True
    assert result["checks"]["quote"]["ok"] is False
    assert "quote unavailable" in result["checks"]["quote"]["error"]
