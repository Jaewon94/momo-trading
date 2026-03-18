"""KIS 브로커 어댑터"""
from datetime import datetime

from trading.account_manager import account_manager
from trading.adapters.base import (
    AccountClientProtocol,
    BrokerAdapter,
    MarketDataClientProtocol,
    OrderExecutorProtocol,
)
from trading.enums import BrokerProvider, Market
from trading.mcp_client import mcp_client
from trading.models import (
    AccountBalance,
    BrokerCapabilities,
    Candle,
    CurrentPrice,
    HoldingInfo,
    OrderRequest,
    OrderResult,
    PendingOrderInfo,
)
from trading.order_executor import order_executor


class KisBrokerAdapter(BrokerAdapter):
    """KIS 의존 구현을 공통 브로커 인터페이스 뒤로 숨긴다."""

    provider = BrokerProvider.KIS
    capabilities = BrokerCapabilities(
        supports_domestic_stocks=True,
        supports_overseas_stocks=True,
        supports_paper_trading=True,
        supports_live_trading=True,
        supports_realtime_quotes=True,
        supports_order_cancellation=True,
    )

    def __init__(
        self,
        account_client: AccountClientProtocol = account_manager,
        market_data_client: MarketDataClientProtocol = mcp_client,
        order_executor: OrderExecutorProtocol = order_executor,
    ) -> None:
        self._account_client = account_client
        self._market_data_client = market_data_client
        self._order_executor = order_executor

    async def get_balance(self) -> AccountBalance:
        return await self._account_client.get_balance()

    async def get_holdings(self) -> list[HoldingInfo]:
        return await self._account_client.get_holdings()

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return await self._account_client.get_pending_orders()

    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        response = await self._market_data_client.get_current_price(
            symbol,
            market=market.value,
        )
        self._ensure_success(response.success, response.error)

        data = response.data or {}
        return CurrentPrice(
            symbol=symbol,
            market=market,
            price=float(data.get("current_price") or data.get("price") or 0.0),
            change=float(data.get("change") or 0.0),
            change_rate=float(data.get("change_rate") or 0.0),
            volume=int(data.get("volume") or 0),
            timestamp=datetime.now(),
        )

    async def get_daily_candles(
        self,
        symbol: str,
        count: int = 30,
        market: Market = Market.KOSPI,
    ) -> list[Candle]:
        response = await self._market_data_client.get_daily_price(
            symbol,
            count=count,
            market=market.value,
        )
        self._ensure_success(response.success, response.error)
        return self._normalize_candles(response.data or {}, time_key_field="date")

    async def get_intraday_candles(
        self,
        symbol: str,
        interval: str = "5",
        market: Market = Market.KOSPI,
    ) -> list[Candle]:
        response = await self._market_data_client.get_minute_price(
            symbol,
            period=interval,
            market=market.value,
        )
        self._ensure_success(response.success, response.error)
        return self._normalize_candles(response.data or {}, time_key_field="time")

    async def place_order(self, request: OrderRequest) -> OrderResult:
        return await self._order_executor.execute(request)

    async def cancel_order(
        self,
        order_id: str,
        market: Market = Market.KOSPI,
    ) -> OrderResult:
        return await self._order_executor.cancel(order_id, market=market.value)

    @staticmethod
    def _normalize_candles(data: dict, time_key_field: str) -> list[Candle]:
        prices = data.get("prices", [])
        candles: list[Candle] = []
        for item in prices:
            candles.append(
                Candle(
                    time_key=str(item.get(time_key_field, "")),
                    open=float(item.get("open") or 0.0),
                    high=float(item.get("high") or 0.0),
                    low=float(item.get("low") or 0.0),
                    close=float(item.get("close") or 0.0),
                    volume=int(item.get("volume") or 0),
                )
            )
        return candles

    @staticmethod
    def _ensure_success(success: bool, error: str | None) -> None:
        if not success:
            raise RuntimeError(error or "브로커 요청 실패")
