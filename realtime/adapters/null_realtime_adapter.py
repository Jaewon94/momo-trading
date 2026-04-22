"""실시간 미지원 브로커용 no-op 어댑터."""
import asyncio
from typing import Any


class NullRealtimeAdapter:
    """실시간 WebSocket을 제공하지 않는 브로커용 no-op 구현."""

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
        await asyncio.sleep(1)

    @property
    def subscription_count(self) -> int:
        return 0

    @property
    def is_connected(self) -> bool:
        return False
