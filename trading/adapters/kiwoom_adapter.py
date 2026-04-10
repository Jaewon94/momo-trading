"""Kiwoom 브로커 어댑터"""
from dataclasses import dataclass
from datetime import datetime

from trading.adapters.base import (
    AccountClientProtocol,
    BrokerAdapter,
    MarketDataClientProtocol,
    OrderExecutorProtocol,
)
from trading.enums import BrokerProvider, Market, OrderSession
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
from trading.symbols import normalize_krx_symbol


class KiwoomBrokerAdapter(BrokerAdapter):
    """키움 REST 응답을 공통 거래 모델로 정규화한다."""

    provider = BrokerProvider.KIWOOM
    capabilities = BrokerCapabilities(
        supports_domestic_stocks=True,
        supports_overseas_stocks=False,
        supports_paper_trading=True,
        supports_live_trading=True,
        supports_realtime_quotes=False,
        supports_order_cancellation=False,
        supports_nxt_quotes=False,
        supports_after_hours_orders=False,
        supports_after_hours_automation=False,
        supported_order_sessions=[OrderSession.REGULAR],
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
        self._submitted_orders: dict[str, _SubmittedOrderMeta] = {}

    async def get_balance(self) -> AccountBalance:
        return await self._require_account_client().get_balance()

    async def get_holdings(self) -> list[HoldingInfo]:
        return await self._require_account_client().get_holdings()

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return await self._require_account_client().get_pending_orders()

    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        symbol = normalize_krx_symbol(symbol)
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
        symbol = normalize_krx_symbol(symbol)
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
        symbol = normalize_krx_symbol(symbol)
        response = await self._require_market_data_client().get_minute_price(
            symbol,
            period=interval,
            market=market.value,
        )
        self._ensure_success(response.success, response.error)
        return self._normalize_candles(response.data or {}, time_key_field="time")

    async def get_volume_rank(self, market: Market = Market.KRX) -> list[dict]:
        response = await self._require_market_data_client().get_volume_rank(market=market.value)
        if response.success and response.data:
            return response.data.get("stocks", response.data.get("items", []))
        return []

    async def get_fluctuation_rank(
        self,
        sort: str,
        market: Market = Market.KRX,
    ) -> list[dict]:
        response = await self._require_market_data_client().get_fluctuation_rank(
            sort=sort,
            market=market.value,
        )
        if response.success and response.data:
            return response.data.get("stocks", response.data.get("items", []))
        return []

    async def place_order(self, request: OrderRequest) -> OrderResult:
        normalized_symbol = normalize_krx_symbol(request.symbol)
        baseline_qty = await self._get_holding_quantity(normalized_symbol)
        normalized_request = request.model_copy(update={"symbol": normalized_symbol})
        result = await self._require_order_executor().execute(normalized_request)
        if result.success and result.order_id:
            self._submitted_orders[str(result.order_id)] = _SubmittedOrderMeta(
                symbol=normalized_symbol,
                side=request.side.value,
                quantity=request.quantity,
                order_price=float(request.price or 0.0),
                baseline_qty=baseline_qty,
            )
        return result

    async def cancel_order(
        self,
        order_id: str,
        market: Market = Market.KRX,
    ) -> OrderResult:
        return await self._require_order_executor().cancel(order_id, market=market.value)

    async def get_buying_power(
        self,
        symbol: str,
        price: float | None = None,
        market: Market = Market.KRX,
    ) -> BuyingPowerInfo:
        resolved_price = float(price or 0.0)
        if resolved_price <= 0:
            quote = await self.get_current_price(symbol, market=market)
            resolved_price = float(quote.price or 0.0)

        balance = await self.get_balance()
        available_cash = max(float(balance.cash or 0.0), 0.0)
        max_qty = int(available_cash // resolved_price) if resolved_price > 0 else 0
        return BuyingPowerInfo(
            success=resolved_price > 0,
            max_qty=max_qty,
            available_cash=available_cash,
        )

    async def get_order_status(self, order_id: str) -> OrderStatusInfo | None:
        pending_orders = await self.get_pending_orders()
        for order in pending_orders:
            if order.order_id != order_id:
                continue
            filled_price = order.order_price if order.filled_qty > 0 else 0.0
            if filled_price <= 0:
                submitted = self._submitted_orders.get(str(order_id))
                holding = await self._get_holding(order.symbol)
                if holding is not None and holding.avg_buy_price > 0:
                    filled_price = holding.avg_buy_price
                elif submitted is not None and submitted.order_price > 0:
                    filled_price = submitted.order_price
            return OrderStatusInfo(
                order_id=order.order_id,
                symbol=order.symbol,
                filled_qty=order.filled_qty,
                filled_price=filled_price,
                remaining_qty=order.remaining_qty,
                order_price=filled_price if filled_price > 0 else order.order_price,
            )

        submitted = self._submitted_orders.get(str(order_id))
        if submitted is None:
            return None

        holding = await self._get_holding(submitted.symbol)
        current_qty = holding.quantity if holding is not None else 0

        if submitted.side == "BUY":
            filled_qty = max(min(current_qty - submitted.baseline_qty, submitted.quantity), 0)
        else:
            filled_qty = max(min(submitted.baseline_qty - current_qty, submitted.quantity), 0)

        if filled_qty <= 0:
            return None

        filled_price = submitted.order_price
        if filled_price <= 0 and holding is not None:
            filled_price = holding.avg_buy_price

        return OrderStatusInfo(
            order_id=str(order_id),
            symbol=submitted.symbol,
            filled_qty=filled_qty,
            filled_price=filled_price,
            remaining_qty=max(submitted.quantity - filled_qty, 0),
            order_price=filled_price,
        )

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

    async def _get_holding(self, symbol: str) -> HoldingInfo | None:
        symbol = normalize_krx_symbol(symbol)
        holdings = await self.get_holdings()
        for holding in holdings:
            if normalize_krx_symbol(holding.symbol) == symbol:
                return holding
        return None

    async def _get_holding_quantity(self, symbol: str) -> int:
        holding = await self._get_holding(symbol)
        return holding.quantity if holding is not None else 0

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


@dataclass(slots=True)
class _SubmittedOrderMeta:
    symbol: str
    side: str
    quantity: int
    order_price: float
    baseline_qty: int
