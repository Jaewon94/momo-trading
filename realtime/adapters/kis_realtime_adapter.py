"""KIS 실시간 어댑터."""
from trading.kis_websocket import kis_websocket


class KISRealtimeAdapter:
    """기존 KIS WebSocket 구현을 공통 실시간 계약 뒤로 숨긴다."""

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
