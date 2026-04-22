"""실시간 이벤트 감지 — 종목별 AI 설정 임계값 기반"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from core.events import Event, EventType, event_bus


@dataclass
class StockThresholds:
    """종목별 감시 임계값 (AI가 종목 선정 시 설정)"""
    surge_pct: float = 3.0        # 급등 기준 (%)
    drop_pct: float = -3.0        # 급락 기준 (%)
    volume_spike_ratio: float = 3.0  # 거래량 급증 배수
    stop_loss: float = 0.0        # 손절 가격
    take_profit: float = 0.0      # 익절 가격
    trailing_stop_pct: float = 0.0   # 트레일링 스탑 (%, 0이면 미사용)

    # 트레일링 스탑용 고점 추적
    highest_price: float = 0.0


# 기본 임계값 (AI 미설정 시 폴백)
DEFAULT_THRESHOLDS = StockThresholds()

EVENT_LABELS = {
    EventType.VOLUME_SPIKE: "거래량 급증",
    EventType.PRICE_SURGE: "급등",
    EventType.PRICE_DROP: "급락",
    EventType.STOP_LOSS_HIT: "손절 도달",
    EventType.TAKE_PROFIT_HIT: "익절 도달",
}


class EventDetector:
    """
    실시간 가격 데이터에서 이벤트 감지 — 종목별 임계값 기반

    AI Agent가 종목 선정 시 set_thresholds()로 종목별 기준을 설정하고,
    WebSocket 체결 데이터가 들어올 때마다 해당 기준으로 이벤트를 감지한다.
    """

    def __init__(self):
        # 종목별 임계값 (AI가 설정)
        self._thresholds: dict[str, StockThresholds] = {}

        # 실시간 데이터 캐시
        self._prev_prices: dict[str, float] = {}
        self._volume_history: dict[str, list[int]] = defaultdict(list)

        # 이벤트 중복 발행 방지 (종목별 마지막 이벤트 타입+시간)
        self._last_events: dict[str, tuple[str, float]] = {}
        self.EVENT_DEDUP_SEC = 60  # 같은 이벤트 60초 내 재발행 방지
        self._recent_events: list[dict] = []
        self.MAX_RECENT_EVENTS = 40

    def set_thresholds(self, symbol: str, **kwargs) -> None:
        """종목별 감시 임계값 설정 (AI Agent가 호출)

        사용 예:
            event_detector.set_thresholds("005930",
                surge_pct=2.0, drop_pct=-2.0,
                volume_spike_ratio=2.5,
                stop_loss=71000, take_profit=76000,
                trailing_stop_pct=2.0,
            )
        """
        import math

        # 값 검증: NaN, None, 숫자가 아닌 값 필터링
        validated = {}
        for k, v in kwargs.items():
            if isinstance(v, (int, float)) and not math.isnan(v):
                validated[k] = v
            else:
                logger.warning("유효하지 않은 임계값 무시: {} {} = {}", symbol, k, v)

        if symbol in self._thresholds:
            th = self._thresholds[symbol]
            for k, v in validated.items():
                if hasattr(th, k):
                    setattr(th, k, v)
        else:
            self._thresholds[symbol] = StockThresholds(**validated)

        # trailing_stop 설정 시 highest_price를 stop_loss 기반으로 초기화
        th = self._thresholds[symbol]
        if 0 < th.trailing_stop_pct < 100 and th.highest_price == 0 and th.stop_loss > 0:
            # stop_loss = highest × (1 - pct/100) → highest = stop_loss / (1 - pct/100)
            th.highest_price = th.stop_loss / (1 - th.trailing_stop_pct / 100)

        logger.debug("임계값 설정: {} → {}", symbol, self._thresholds[symbol])

    def get_thresholds(self, symbol: str) -> StockThresholds:
        return self._thresholds.get(symbol, DEFAULT_THRESHOLDS)

    def set_stop_loss(self, symbol: str, price: float) -> None:
        self.set_thresholds(symbol, stop_loss=price)

    def set_take_profit(self, symbol: str, price: float) -> None:
        self.set_thresholds(symbol, take_profit=price)

    def remove_levels(self, symbol: str) -> None:
        self._thresholds.pop(symbol, None)

    def clear_all(self) -> None:
        """전체 초기화 (장 시작 시)"""
        self._thresholds.clear()
        self._prev_prices.clear()
        self._volume_history.clear()
        self._last_events.clear()
        self._recent_events.clear()

    @property
    def monitored_symbols(self) -> list[str]:
        return list(self._thresholds.keys())

    async def on_price_update(self, data: dict) -> None:
        """실시간 가격 업데이트 처리 + 이벤트 감지"""
        # 장외 시간: 이벤트 감지 불필요
        from scheduler.market_calendar import market_calendar
        if not market_calendar.is_krx_trading_hours():
            return

        symbol = data.get("symbol", "")
        price = data.get("price", 0)
        volume = data.get("volume", 0)
        change_rate = data.get("change_rate", 0)

        if not symbol or price <= 0:
            return

        th = self.get_thresholds(symbol)
        automated_trading_allowed = market_calendar.is_automated_trading_session()
        enriched_data = {**data, "order_allowed": automated_trading_allowed}

        # 가격 업데이트 이벤트 발행
        await event_bus.publish(Event(
            type=EventType.PRICE_UPDATE,
            data=enriched_data,
            source="event_detector",
        ))

        # 트레일링 스탑 고점 갱신
        if th.trailing_stop_pct > 0 and price > th.highest_price:
            th.highest_price = price
            # 트레일링 스탑 가격 = 고점 × (1 - trailing_pct/100)
            new_stop = price * (1 - th.trailing_stop_pct / 100)
            if new_stop > th.stop_loss:
                th.stop_loss = new_stop
                logger.debug("트레일링 스탑 상향: {} → 손절 {:,.0f}원 (고점 {:,.0f})",
                             symbol, new_stop, price)

        # 거래량 급증 감지
        if not automated_trading_allowed:
            self._prev_prices[symbol] = price
            self._volume_history[symbol].append(volume)
            if len(self._volume_history[symbol]) > 20:
                self._volume_history[symbol] = self._volume_history[symbol][-20:]
            return

        await self._check_volume_spike(symbol, volume, th, enriched_data)

        # 급등/급락 감지
        await self._check_price_movement(symbol, price, change_rate, th, enriched_data)

        # 손절/익절 감지
        await self._check_stop_take(symbol, price, th, enriched_data)

        # 캐시 업데이트
        self._prev_prices[symbol] = price
        self._volume_history[symbol].append(volume)
        if len(self._volume_history[symbol]) > 20:
            self._volume_history[symbol] = self._volume_history[symbol][-20:]

    async def _check_volume_spike(
        self, symbol: str, volume: int, th: StockThresholds, data: dict,
    ) -> None:
        history = self._volume_history.get(symbol, [])
        if len(history) < 5:
            return

        avg_volume = sum(history[-10:]) / len(history[-10:])
        if avg_volume > 0 and volume > avg_volume * th.volume_spike_ratio:
            if not self._should_dedup(symbol, "VOLUME_SPIKE"):
                spike_ratio = volume / avg_volume
                logger.debug("거래량 급증: {} ({:.1f}배, 기준 {:.1f}배)",
                            symbol, spike_ratio, th.volume_spike_ratio)
                event = Event(
                    type=EventType.VOLUME_SPIKE,
                    data={**data, "avg_volume": avg_volume, "spike_ratio": spike_ratio},
                    source="event_detector",
                )
                self._record_recent_event(event)
                await event_bus.publish(event)

    async def _check_price_movement(
        self, symbol: str, price: float, change_rate: float,
        th: StockThresholds, data: dict,
    ) -> None:
        if change_rate >= th.surge_pct:
            if not self._should_dedup(symbol, "PRICE_SURGE"):
                logger.debug("급등: {} ({:+.2f}%, 기준 {:.1f}%)",
                            symbol, change_rate, th.surge_pct)
                event = Event(
                    type=EventType.PRICE_SURGE,
                    data=data,
                    source="event_detector",
                )
                self._record_recent_event(event)
                await event_bus.publish(event)
        elif change_rate <= th.drop_pct:
            if not self._should_dedup(symbol, "PRICE_DROP"):
                logger.debug("급락: {} ({:+.2f}%, 기준 {:.1f}%)",
                            symbol, change_rate, th.drop_pct)
                event = Event(
                    type=EventType.PRICE_DROP,
                    data=data,
                    source="event_detector",
                )
                self._record_recent_event(event)
                await event_bus.publish(event)

    async def _check_stop_take(
        self, symbol: str, price: float, th: StockThresholds, data: dict,
    ) -> None:
        if th.stop_loss > 0 and price <= th.stop_loss:
            if not self._should_dedup(symbol, "STOP_LOSS"):
                logger.warning("손절선 도달: {} (현재 {:,.0f}, 손절 {:,.0f})",
                               symbol, price, th.stop_loss)
                event = Event(
                    type=EventType.STOP_LOSS_HIT,
                    data={**data, "stop_loss_price": th.stop_loss},
                    source="event_detector",
                )
                self._record_recent_event(event)
                await event_bus.publish(event)

        if th.take_profit > 0 and price >= th.take_profit:
            if not self._should_dedup(symbol, "TAKE_PROFIT"):
                logger.debug("익절선 도달: {} (현재 {:,.0f}, 익절 {:,.0f})",
                            symbol, price, th.take_profit)
                event = Event(
                    type=EventType.TAKE_PROFIT_HIT,
                    data={**data, "take_profit_price": th.take_profit},
                    source="event_detector",
                )
                self._record_recent_event(event)
                await event_bus.publish(event)

    def _record_recent_event(self, event: Event) -> None:
        import time

        data = event.data or {}
        symbol = str(data.get("symbol", "")).strip()
        if not symbol:
            return

        change_rate = float(data.get("change_rate", 0.0) or 0.0)
        volume_ratio = float(data.get("spike_ratio", 0.0) or 0.0)
        price = float(data.get("price", 0.0) or 0.0)
        cooldown_until = event.timestamp.timestamp() + self.EVENT_DEDUP_SEC

        payload = {
            "symbol": symbol,
            "name": str(data.get("name") or symbol),
            "event_type": event.type.value,
            "event_label": EVENT_LABELS.get(event.type, event.type.value),
            "score": self._score_event(event.type, change_rate=change_rate, volume_ratio=volume_ratio),
            "state": self._event_state(event.type),
            "direction": self._event_direction(event.type),
            "occurred_at": event.timestamp.isoformat(),
            "cooldown_until": datetime.fromtimestamp(cooldown_until).isoformat(),
            "cooldown_remaining_sec": max(0, int(cooldown_until - time.time())),
            "price": price,
            "change_rate": change_rate,
            "volume_ratio": volume_ratio,
            "reason": self._event_reason(event.type, data),
        }

        self._recent_events = [
            item for item in self._recent_events
            if not (item.get("symbol") == symbol and item.get("event_type") == event.type.value)
        ]
        self._recent_events.insert(0, payload)
        self._recent_events = self._recent_events[: self.MAX_RECENT_EVENTS]

    def _event_state(self, event_type: EventType) -> str:
        if event_type in {EventType.STOP_LOSS_HIT, EventType.TAKE_PROFIT_HIT}:
            return "ACTIONABLE"
        return "TRIGGERED"

    def _event_direction(self, event_type: EventType) -> str:
        if event_type in {EventType.STOP_LOSS_HIT, EventType.TAKE_PROFIT_HIT, EventType.PRICE_DROP}:
            return "SELL"
        if event_type == EventType.PRICE_SURGE:
            return "BUY"
        return "WATCH"

    def _event_reason(self, event_type: EventType, data: dict) -> str:
        if event_type == EventType.STOP_LOSS_HIT:
            return "손절가 도달"
        if event_type == EventType.TAKE_PROFIT_HIT:
            return "목표가 도달"
        if event_type == EventType.PRICE_SURGE:
            return "가격 급등"
        if event_type == EventType.PRICE_DROP:
            return "가격 급락"
        if event_type == EventType.VOLUME_SPIKE:
            return "거래량 급증"
        return str(data.get("reason") or "")

    def _score_event(self, event_type: EventType, *, change_rate: float, volume_ratio: float) -> int:
        if event_type in {EventType.STOP_LOSS_HIT, EventType.TAKE_PROFIT_HIT}:
            return 92

        score = 40
        score += min(30, int(abs(change_rate) * 6))
        score += min(20, int(max(0.0, volume_ratio - 1.0) * 8))
        if event_type == EventType.VOLUME_SPIKE:
            score += 8
        return min(99, max(0, score))

    def get_radar_snapshot(self) -> dict:
        import time
        now = time.time()
        events = []
        for item in self._recent_events:
            cooldown_until = item.get("cooldown_until")
            remaining = 0
            if cooldown_until:
                try:
                    remaining = max(0, int(datetime.fromisoformat(cooldown_until).timestamp() - now))
                except ValueError:
                    remaining = 0
            payload = {
                **item,
                "state": item.get("state") if remaining <= 0 else "COOLDOWN",
                "cooldown_remaining_sec": remaining,
            }
            events.append(payload)

        events.sort(
            key=lambda item: (
                1 if item.get("state") == "ACTIONABLE" else 0,
                item.get("score") or 0,
                item.get("occurred_at") or "",
            ),
            reverse=True,
        )

        return {
            "summary": {
                "total": len(events),
                "actionable": sum(1 for item in events if item.get("state") == "ACTIONABLE"),
                "cooldown": sum(1 for item in events if item.get("state") == "COOLDOWN"),
                "buy_candidates": sum(1 for item in events if item.get("direction") == "BUY"),
                "sell_candidates": sum(1 for item in events if item.get("direction") == "SELL"),
            },
            "events": events,
        }

    def _should_dedup(self, symbol: str, event_type: str) -> bool:
        """같은 종목+이벤트 중복 발행 방지"""
        import time
        key = f"{symbol}:{event_type}"
        now = time.time()
        last = self._last_events.get(key)
        if last and now - last[1] < self.EVENT_DEDUP_SEC:
            return True
        self._last_events[key] = (event_type, now)
        return False


event_detector = EventDetector()
