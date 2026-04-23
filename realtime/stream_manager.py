"""WebSocket 연결 관리 - 동적 구독/해제, 재연결"""
import asyncio
from dataclasses import dataclass
from enum import IntEnum

from loguru import logger

from realtime.adapters.base import RealtimeAdapter
from realtime.realtime_factory import get_realtime_adapter


class SubscriptionPriority(IntEnum):
    NEW_CANDIDATE = 10
    ACTIVE_THRESHOLD = 20
    PENDING_ORDER = 30
    HELD_POSITION = 40


@dataclass(frozen=True)
class SubscriptionRequest:
    symbol: str
    market: str = "KRX"
    priority: SubscriptionPriority = SubscriptionPriority.NEW_CANDIDATE


class StreamManager:
    """
    WebSocket 스트림 관리자
    - KIS 제한: 세션당 41종목
    - AI 선정 종목만 동적 구독/해제
    - 끊김 시 자동 재연결
    """

    MAX_SUBSCRIPTIONS = 41

    def __init__(self, realtime_adapter: RealtimeAdapter | None = None):
        self._subscriptions: dict[str, SubscriptionRequest] = {}
        self._polling_fallback_symbols: list[str] = []
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

    async def subscribe_symbols(self, symbols: list[tuple[str, str] | SubscriptionRequest]) -> None:
        """종목 리스트 구독 (symbol, market) 쌍"""
        combined = list(self._subscriptions.values()) + self._normalize_requests(symbols)
        await self._apply_subscription_plan(combined)

    async def unsubscribe_symbols(self, symbols: list[str]) -> None:
        """종목 구독 해제"""
        for symbol in symbols:
            existing = self._subscriptions.pop(symbol, None)
            market = existing.market if existing else "KRX"
            await self._realtime_adapter.unsubscribe(symbol, market)

    async def update_subscriptions(self, new_symbols: list[tuple[str, str] | SubscriptionRequest]) -> None:
        """AI가 선정한 새 종목으로 구독 목록 업데이트"""
        await self._apply_subscription_plan(new_symbols)

    async def _apply_subscription_plan(self, new_symbols: list[tuple[str, str] | SubscriptionRequest]) -> None:
        planned, fallback = self._build_subscription_plan(new_symbols)
        self._mark_fallback(fallback, replace=True)

        new_set = {request.symbol for request in planned}
        current_set = set(self._subscriptions.keys())

        # 해제할 종목
        to_remove = current_set - new_set
        if to_remove:
            await self.unsubscribe_symbols(list(to_remove))

        # 추가할 종목
        to_add = [request for request in planned if request.symbol not in current_set]
        for request in to_add:
            success = await self._realtime_adapter.subscribe(request.symbol, request.market)
            if success:
                self._subscriptions[request.symbol] = request

        # priority만 바뀐 기존 종목도 내부 상태는 최신 plan으로 맞춘다.
        for request in planned:
            if request.symbol in self._subscriptions:
                self._subscriptions[request.symbol] = request

    def _normalize_requests(self, symbols: list[tuple[str, str] | SubscriptionRequest]) -> list[SubscriptionRequest]:
        requests: list[SubscriptionRequest] = []
        for item in symbols:
            if isinstance(item, SubscriptionRequest):
                if item.symbol:
                    requests.append(item)
                continue
            symbol, market = item
            if symbol:
                requests.append(SubscriptionRequest(symbol=symbol, market=market))
        return requests

    def _build_subscription_plan(
        self,
        symbols: list[tuple[str, str] | SubscriptionRequest],
    ) -> tuple[list[SubscriptionRequest], list[SubscriptionRequest]]:
        deduped: dict[str, tuple[int, SubscriptionRequest]] = {}
        for index, request in enumerate(self._normalize_requests(symbols)):
            existing = deduped.get(request.symbol)
            if existing is None or request.priority > existing[1].priority:
                deduped[request.symbol] = (index, request)

        ordered = [
            request
            for _index, request in sorted(
                deduped.values(),
                key=lambda item: (-int(item[1].priority), item[0]),
            )
        ]
        return ordered[:self.MAX_SUBSCRIPTIONS], ordered[self.MAX_SUBSCRIPTIONS:]

    def _mark_fallback(self, requests: list[SubscriptionRequest], *, replace: bool = False) -> None:
        if replace:
            self._polling_fallback_symbols = []
        seen = set(self._polling_fallback_symbols)
        for request in requests:
            if request.symbol not in seen:
                self._polling_fallback_symbols.append(request.symbol)
                seen.add(request.symbol)

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
                        for request in self._subscriptions.values():
                            await self._realtime_adapter.subscribe(request.symbol, request.market)
                    except Exception as re:
                        logger.error("재연결 실패: {}", str(re))

    @property
    def subscription_count(self) -> int:
        return self._realtime_adapter.subscription_count

    @property
    def is_connected(self) -> bool:
        return self._realtime_adapter.is_connected

    @property
    def polling_fallback_symbols(self) -> list[str]:
        return list(self._polling_fallback_symbols)

    @property
    def skipped_subscription_count(self) -> int:
        return len(self._polling_fallback_symbols)


stream_manager = StreamManager()
