"""Kiwoom 브로커 어댑터"""
from datetime import datetime

from trading.adapters.base import (
    AccountClientProtocol,
    BrokerAdapter,
    MarketDataClientProtocol,
    OrderExecutorProtocol,
)
from trading.enums import BrokerProvider, Market
from trading.models import (
    AccountBalance,
    BrokerCapabilities,
    Candle,
    CurrentPrice,
    HoldingInfo,
    OrderRequest,
    OrderResult,
    OrderStatusInfo,
    PendingOrderInfo,
)


class KiwoomBrokerAdapter(BrokerAdapter):
    """키움 REST 응답을 공통 거래 모델로 정규화한다."""

    provider = BrokerProvider.KIWOOM
    capabilities = BrokerCapabilities(
        supports_domestic_stocks=True,
        supports_overseas_stocks=False,
        supports_paper_trading=True,
        supports_live_trading=True,
        supports_realtime_quotes=True,
        supports_order_cancellation=False,
    )

    def __init__(
        self,
        account_client: AccountClientProtocol | None = None,
        market_data_client: MarketDataClientProtocol | None = None,
        order_executor: OrderExecutorProtocol | None = None,
    ) -> None:
        self._account_client = account_client
        self._market_data_client = market_data_client
        self._order_executor = order_executor

    async def get_balance(self) -> AccountBalance:
        return await self._require_account_client().get_balance()

    async def get_holdings(self) -> list[HoldingInfo]:
        return await self._require_account_client().get_holdings()

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return await self._require_account_client().get_pending_orders()

    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        response = await self._require_market_data_client().get_current_price(
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
        market: Market = Market.KRX,
    ) -> list[Candle]:
        response = await self._require_market_data_client().get_daily_price(
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
        market: Market = Market.KRX,
    ) -> list[Candle]:
        response = await self._require_market_data_client().get_minute_price(
            symbol,
            period=interval,
            market=market.value,
        )
        self._ensure_success(response.success, response.error)
        return self._normalize_candles(response.data or {}, time_key_field="time")

    async def get_volume_rank(self, market: Market = Market.KRX) -> list[dict]:
        return []

    async def get_fluctuation_rank(
        self,
        sort: str,
        market: Market = Market.KRX,
    ) -> list[dict]:
        return []

    async def place_order(self, request: OrderRequest) -> OrderResult:
        return await self._require_order_executor().execute(request)

    async def cancel_order(
        self,
        order_id: str,
        market: Market = Market.KRX,
    ) -> OrderResult:
        return await self._require_order_executor().cancel(order_id, market=market.value)

    async def get_order_status(self, order_id: str) -> OrderStatusInfo | None:
        pending_orders = await self.get_pending_orders()
        for order in pending_orders:
            if order.order_id != order_id:
                continue
            return OrderStatusInfo(
                order_id=order.order_id,
                symbol=order.symbol,
                filled_qty=order.filled_qty,
                filled_price=order.order_price if order.filled_qty > 0 else 0.0,
                remaining_qty=order.remaining_qty,
                order_price=order.order_price,
            )
        return None

    def invalidate_cache(self) -> None:
        if hasattr(self._account_client, "invalidate_cache"):
            self._account_client.invalidate_cache()

    def _require_account_client(self) -> AccountClientProtocol:
        if self._account_client is None:
            raise RuntimeError("Kiwoom account client가 구성되지 않았습니다")
        return self._account_client

    def _require_market_data_client(self) -> MarketDataClientProtocol:
        if self._market_data_client is None:
            raise RuntimeError("Kiwoom market data client가 구성되지 않았습니다")
        return self._market_data_client

    def _require_order_executor(self) -> OrderExecutorProtocol:
        if self._order_executor is None:
            raise RuntimeError("Kiwoom order executor가 구성되지 않았습니다")
        return self._order_executor

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
