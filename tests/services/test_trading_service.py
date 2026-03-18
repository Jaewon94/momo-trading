import pytest

from exceptions.common import ServiceException
from services.trading_service import TradingService
from trading.enums import Market, OrderSide, OrderType
from trading.models import AccountBalance, CurrentPrice, OrderRequest, OrderResult


class FakeBrokerAdapter:
    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []

    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_asset=1_200_000,
            cash=400_000,
            stock_value=800_000,
            total_pnl=20_000,
            total_pnl_rate=1.7,
        )

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.orders.append(request)
        return OrderResult(
            success=True,
            order_id="ORD-1",
            message="주문 실행 완료",
            filled_quantity=request.quantity,
            filled_price=request.price or 0.0,
        )

    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        return CurrentPrice(
            symbol=symbol,
            market=market,
            price=71_500,
            change=500,
            change_rate=0.7,
            volume=123456,
            timestamp=__import__("datetime").datetime.now(),
        )


@pytest.mark.asyncio
async def test_trading_service_returns_account_balance() -> None:
    service = TradingService(broker_adapter=FakeBrokerAdapter())

    balance = await service.get_account_balance()

    assert balance.cash == 400_000
    assert balance.stock_value == 800_000


@pytest.mark.asyncio
async def test_trading_service_delegates_order_execution(monkeypatch) -> None:
    adapter = FakeBrokerAdapter()
    service = TradingService(broker_adapter=adapter)
    monkeypatch.setattr("services.trading_service.settings.TRADING_ENABLED", True)
    request = OrderRequest(
        symbol="005930",
        market=Market.KOSPI,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=2,
        price=71_000,
    )

    result = await service.execute_order(request)

    assert result.success is True
    assert result.order_id == "ORD-1"
    assert adapter.orders == [request]


@pytest.mark.asyncio
async def test_trading_service_rejects_orders_when_trading_disabled(monkeypatch) -> None:
    service = TradingService(broker_adapter=FakeBrokerAdapter())
    monkeypatch.setattr("services.trading_service.settings.TRADING_ENABLED", False)
    request = OrderRequest(
        symbol="005930",
        market=Market.KOSPI,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=71_000,
    )

    with pytest.raises(ServiceException) as exc_info:
        await service.execute_order(request)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_trading_service_returns_normalized_quote_dict() -> None:
    service = TradingService(broker_adapter=FakeBrokerAdapter())

    quote = await service.get_current_price("005930", market="KOSPI")

    assert quote["symbol"] == "005930"
    assert quote["market"] == "KOSPI"
    assert quote["price"] == 71_500
