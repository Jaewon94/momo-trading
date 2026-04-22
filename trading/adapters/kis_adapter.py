"""KIS 브로커 어댑터"""
from datetime import datetime

from trading.account_manager import account_manager
from trading.adapters.base import (
    AccountClientProtocol,
    BrokerAdapter,
    MarketDataClientProtocol,
    OrderExecutorProtocol,
)
from trading.enums import BrokerProvider, Market, OrderSession
from trading.mcp_client import mcp_client
from trading.models import (
    AccountBalance,
    BuyingPowerInfo,
    BrokerCapabilities,
    Candle,
    CurrentPrice,
    HoldingInfo,
    OrderRequest,
    OrderResult,
    OrderStatusInfo,
    PendingOrderInfo,
)
from trading.order_executor import order_executor
from trading.kis_api import get_buying_power as get_kis_buying_power


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
        supports_nxt_quotes=True,
        supports_after_hours_orders=False,
        supports_after_hours_automation=False,
        supported_order_sessions=[OrderSession.REGULAR],
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

    async def get_volume_rank(self, market: Market = Market.KRX) -> list[dict]:
        response = await self._market_data_client.get_volume_rank(market=market.value)
        if response.success and response.data:
            return response.data.get("stocks", response.data.get("items", []))
        return []

    async def get_fluctuation_rank(
        self,
        sort: str,
        market: Market = Market.KRX,
    ) -> list[dict]:
        response = await self._market_data_client.get_fluctuation_rank(
            sort=sort,
            market=market.value,
        )
        if response.success and response.data:
            return response.data.get("stocks", response.data.get("items", []))
        return []

    async def place_order(self, request: OrderRequest) -> OrderResult:
        return await self._order_executor.execute(request)

    async def cancel_order(
        self,
        order_id: str,
        market: Market = Market.KOSPI,
    ) -> OrderResult:
        return await self._order_executor.cancel(order_id, market=market.value)

    async def get_buying_power(
        self,
        symbol: str,
        price: float | None = None,
        market: Market = Market.KRX,
    ) -> BuyingPowerInfo:
        result = await get_kis_buying_power(symbol, price=int(price or 0))
        return BuyingPowerInfo(
            success=bool(result.get("success")),
            max_qty=int(result.get("max_qty") or 0),
            available_cash=float(result.get("available_cash") or 0.0),
        )

    async def get_order_status(self, order_id: str) -> OrderStatusInfo | None:
        response = await mcp_client.get_order_list()
        if not response.success:
            return None

        orders = self._extract_orders(response.data or {})
        for order in orders:
            current_order_id = (
                order.get("odno")
                or order.get("ODNO")
                or order.get("order_id")
                or ""
            )
            if str(current_order_id) != str(order_id):
                continue

            order_qty = self._to_int(order.get("ord_qty") or order.get("order_qty"))
            filled_qty = self._to_int(
                order.get("tot_ccld_qty")
                or order.get("filled_quantity")
                or order.get("ccld_qty")
            )
            remaining_qty = self._to_int(order.get("rmn_qty") or order_qty - filled_qty)
            filled_price = self._to_float(
                order.get("avg_prvs")
                or order.get("ccld_pric")
                or order.get("filled_price")
                or order.get("ord_unpr")
            )
            return OrderStatusInfo(
                order_id=str(current_order_id),
                symbol=str(order.get("pdno") or order.get("symbol") or ""),
                filled_qty=filled_qty,
                filled_price=filled_price,
                remaining_qty=max(remaining_qty, 0),
                order_price=self._to_float(order.get("ord_unpr") or order.get("order_price")),
            )
        return None

    def invalidate_cache(self) -> None:
        if hasattr(self._account_client, "invalidate_cache"):
            self._account_client.invalidate_cache()

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

    @staticmethod
    def _extract_orders(data: dict) -> list[dict]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        orders = data.get("output") or data.get("output1") or data.get("orders") or []
        if isinstance(orders, dict):
            return [orders]
        if isinstance(orders, list):
            return [item for item in orders if isinstance(item, dict)]
        return []

    @staticmethod
    def _to_int(value: object) -> int:
        if value in (None, "", "-"):
            return 0
        try:
            return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _to_float(value: object) -> float:
        if value in (None, "", "-"):
            return 0.0
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0
