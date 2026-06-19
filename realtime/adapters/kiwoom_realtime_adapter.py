"""키움 실시간 어댑터."""
from trading.kiwoom_websocket import kiwoom_websocket


class KiwoomRealtimeAdapter:
    """키움 WebSocket 구현을 공통 실시간 계약 뒤로 숨긴다."""

    def set_on_price(self, callback) -> None:
        kiwoom_websocket.set_on_price(callback)

    async def start(self) -> None:
        await kiwoom_websocket.connect()

    async def stop(self) -> None:
        await kiwoom_websocket.disconnect()

    async def subscribe(self, symbol: str, market: str = "KRX") -> bool:
        return await kiwoom_websocket.subscribe(symbol, market)

    async def unsubscribe(self, symbol: str, market: str = "KRX") -> None:
        await kiwoom_websocket.unsubscribe(symbol, market)

    async def listen(self) -> None:
        await kiwoom_websocket.listen()

    @property
    def subscription_count(self) -> int:
        return kiwoom_websocket.subscription_count

    @property
    def is_connected(self) -> bool:
        return kiwoom_websocket.is_connected
