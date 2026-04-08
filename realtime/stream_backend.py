"""브로커별 실시간 스트림 백엔드 선택"""
from functools import lru_cache
from typing import Any, Protocol

from core.config import settings
from trading.kis_websocket import kis_websocket


class StreamBackend(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def subscribe(self, symbol: str, market: str = "KRX") -> bool: ...
    async def unsubscribe(self, symbol: str, market: str = "KRX") -> None: ...
    async def listen(self) -> None: ...
    def set_on_price(self, callback) -> None: ...

    @property
    def subscription_count(self) -> int: ...

    @property
    def is_connected(self) -> bool: ...


class KISStreamBackend:
    """KIS WebSocket 구현 래퍼"""

    def set_on_price(self, callback) -> None:
        kis_websocket.set_on_price(callback)

    async def start(self) -> None:
        await kis_websocket.connect()

    async def stop(self) -> None:
        await kis_websocket.disconnect()

    async def subscribe(self, symbol: str, market: str = "KRX") -> bool:
        return await kis_websocket.subscribe(symbol, market)

    async def unsubscribe(self, symbol: str, market: str = "KRX") -> None:
        await kis_websocket.unsubscribe(symbol, market)

    async def listen(self) -> None:
        await kis_websocket.listen()

    @property
    def subscription_count(self) -> int:
        return kis_websocket.subscription_count

    @property
    def is_connected(self) -> bool:
        return kis_websocket.is_connected


class NullStreamBackend:
    """실시간 WebSocket을 제공하지 않는 브로커용 no-op 백엔드"""

    def __init__(self) -> None:
        self._callback: Any = None

    def set_on_price(self, callback) -> None:
        self._callback = callback

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def subscribe(self, symbol: str, market: str = "KRX") -> bool:
        return False

    async def unsubscribe(self, symbol: str, market: str = "KRX") -> None:
        return None

    async def listen(self) -> None:
        return None

    @property
    def subscription_count(self) -> int:
        return 0

    @property
    def is_connected(self) -> bool:
        return False


@lru_cache(maxsize=1)
def get_stream_backend() -> StreamBackend:
    if settings.BROKER_PROVIDER.upper() == "KIS":
        return KISStreamBackend()
    return NullStreamBackend()
