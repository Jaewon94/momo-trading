"""브로커 어댑터 공통 계약"""
from abc import ABC, abstractmethod
from typing import Protocol

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


class AccountClientProtocol(Protocol):
    async def get_balance(self) -> AccountBalance: ...
    async def get_holdings(self) -> list[HoldingInfo]: ...
    async def get_pending_orders(self) -> list[PendingOrderInfo]: ...


class MarketDataClientProtocol(Protocol):
    async def get_current_price(self, symbol: str, market: str = "KRX"): ...
    async def get_daily_price(
        self,
        symbol: str,
        period: str = "D",
        count: int = 30,
        market: str = "KRX",
    ): ...
    async def get_minute_price(
        self,
        symbol: str,
        period: str = "5",
        market: str = "KRX",
    ): ...
    async def get_volume_rank(self, market: str = "KRX"): ...
    async def get_fluctuation_rank(self, sort: str, market: str = "KRX"): ...


class OrderExecutorProtocol(Protocol):
    async def execute(self, request: OrderRequest) -> OrderResult: ...
    async def cancel(self, order_id: str, market: str = "KRX") -> OrderResult: ...


class BrokerAdapter(ABC):
    """브로커 어댑터 추상 타입"""

    provider: BrokerProvider
    capabilities: BrokerCapabilities

    @abstractmethod
    async def get_balance(self) -> AccountBalance: ...

    @abstractmethod
    async def get_holdings(self) -> list[HoldingInfo]: ...

    @abstractmethod
    async def get_pending_orders(self) -> list[PendingOrderInfo]: ...

    @abstractmethod
    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice: ...

    @abstractmethod
    async def get_daily_candles(
        self,
        symbol: str,
        count: int = 30,
        market: Market = Market.KOSPI,
    ) -> list[Candle]: ...

    @abstractmethod
    async def get_intraday_candles(
        self,
        symbol: str,
        interval: str = "5",
        market: Market = Market.KOSPI,
    ) -> list[Candle]: ...

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(
        self,
        order_id: str,
        market: Market = Market.KOSPI,
    ) -> OrderResult: ...

    async def get_order_status(self, order_id: str) -> OrderStatusInfo | None:
        return None

    def invalidate_cache(self) -> None:
        return None

    async def get_volume_rank(self, market: Market = Market.KRX) -> list[dict]:
        return []

    async def get_fluctuation_rank(
        self,
        sort: str,
        market: Market = Market.KRX,
    ) -> list[dict]:
        return []
