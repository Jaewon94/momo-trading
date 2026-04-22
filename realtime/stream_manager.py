"""WebSocket 연결 관리 - 동적 구독/해제, 재연결"""
import asyncio

from loguru import logger

from realtime.adapters.base import RealtimeAdapter
from realtime.realtime_factory import get_realtime_adapter


class StreamManager:
    """
    WebSocket 스트림 관리자
    - KIS 제한: 세션당 41종목
    - AI 선정 종목만 동적 구독/해제
    - 끊김 시 자동 재연결
    """

    def __init__(self, realtime_adapter: RealtimeAdapter | None = None):
        self._priority_symbols: dict[str, str] = {}  # symbol -> market
        self._running = False
        self._listen_task: asyncio.Task | None = None
        self._realtime_adapter = realtime_adapter or get_realtime_adapter()

    def set_on_price(self, callback) -> None:
        self._realtime_adapter.set_on_price(callback)

    async def start(self) -> None:
        """스트림 관리 시작"""
        self._running = True
        try:
            await self._realtime_adapter.start()
            self._listen_task = asyncio.create_task(self._run_listener())
            logger.debug("스트림 매니저 시작")
        except Exception as e:
            logger.warning("WebSocket 연결 실패 (나중에 재시도): {}", str(e))

    async def stop(self) -> None:
        """스트림 관리 중지"""
        self._running = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        await self._realtime_adapter.stop()
        logger.debug("스트림 매니저 중지")

    async def subscribe_symbols(self, symbols: list[tuple[str, str]]) -> None:
        """종목 리스트 구독 (symbol, market) 쌍"""
        for symbol, market in symbols:
            if self._realtime_adapter.subscription_count >= 41:
                logger.warning("구독 한도 도달 (41종목), 우선순위 낮은 종목 해제 필요")
                break
            success = await self._realtime_adapter.subscribe(symbol, market)
            if success:
                self._priority_symbols[symbol] = market

    async def unsubscribe_symbols(self, symbols: list[str]) -> None:
        """종목 구독 해제"""
        for symbol in symbols:
            market = self._priority_symbols.pop(symbol, "KRX")
            await self._realtime_adapter.unsubscribe(symbol, market)

    async def update_subscriptions(self, new_symbols: list[tuple[str, str]]) -> None:
        """AI가 선정한 새 종목으로 구독 목록 업데이트"""
        new_set = {s[0] for s in new_symbols}
        current_set = set(self._priority_symbols.keys())

        # 해제할 종목
        to_remove = current_set - new_set
        if to_remove:
            await self.unsubscribe_symbols(list(to_remove))

        # 추가할 종목
        to_add = [(s, m) for s, m in new_symbols if s not in current_set]
        if to_add:
            await self.subscribe_symbols(to_add)

    async def _run_listener(self) -> None:
        """WebSocket 수신 루프 (재연결 포함)"""
        while self._running:
            try:
                await self._realtime_adapter.listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("WebSocket 리스너 오류: {}", str(e))
                if self._running:
                    logger.debug("5초 후 재연결 시도...")
                    await asyncio.sleep(5)
                    try:
                        await self._realtime_adapter.start()
                        # 기존 구독 복원
                        for symbol, market in self._priority_symbols.items():
                            await self._realtime_adapter.subscribe(symbol, market)
                    except Exception as re:
                        logger.error("재연결 실패: {}", str(re))

    @property
    def subscription_count(self) -> int:
        return self._realtime_adapter.subscription_count

    @property
    def is_connected(self) -> bool:
        return self._realtime_adapter.is_connected


stream_manager = StreamManager()
