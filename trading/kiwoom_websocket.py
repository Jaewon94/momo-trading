"""Kiwoom WebSocket 실시간 시세 스트리밍.

키움증권 REST API WebSocket 프로토콜(JSON):
  - 접속 후 LOGIN(token) 전송 → return_code 0 이면 성공
  - REG(type "0B" 주식체결)로 종목 실시간 등록 → REAL 메시지로 현재가 수신
  - 서버가 보내는 PING 은 받은 그대로 echo
서버/엔드포인트는 모의(mock)/실전(real)에 따라 자동 전환된다.
WS 가 실패하면 상위 monitor 가 폴링 폴백으로 안전하게 떨어진다(capability=True 여도).
"""
import asyncio
import json
from typing import Any, Callable, Coroutine

import websockets
from loguru import logger

from trading.kiwoom_rest_client import KiwoomRESTClient
from trading.symbols import normalize_krx_symbol


def _ws_is_closed(ws) -> bool:
    """websockets 버전 호환 연결 상태 확인."""
    if ws is None:
        return True
    if hasattr(ws, "closed"):
        return ws.closed
    return ws.close_code is not None


class KiwoomWebSocket:
    """키움증권 WebSocket 실시간 시세 클라이언트."""

    REAL_WS_URL = "wss://api.kiwoom.com:10000/api/dostk/websocket"
    MOCK_WS_URL = "wss://mockapi.kiwoom.com:10000/api/dostk/websocket"
    MAX_SUBSCRIPTIONS = 41
    REALTIME_TYPE = "0B"  # 주식체결(현재가)
    LOGIN_TIMEOUT_SEC = 10

    def __init__(self) -> None:
        self._ws = None
        self._running = False
        self._logged_in = False
        self._subscriptions: set[str] = set()
        self._on_price_callback: Callable[[dict], Coroutine[Any, Any, None]] | None = None
        self._rest_client = KiwoomRESTClient()
        self._lock = asyncio.Lock()

    def set_on_price(self, callback: Callable[[dict], Coroutine[Any, Any, None]]) -> None:
        self._on_price_callback = callback

    @property
    def _ws_url(self) -> str:
        return self.MOCK_WS_URL if self._rest_client.is_paper_trading else self.REAL_WS_URL

    async def connect(self) -> None:
        self._running = True
        await self._ensure_connection()

    async def disconnect(self) -> None:
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        self._logged_in = False
        self._subscriptions.clear()
        logger.debug("Kiwoom WebSocket 연결 종료")

    async def _ensure_connection(self) -> bool:
        """연결+LOGIN 보장. 실패 시 False(상위에서 폴링 폴백)."""
        if self._ws is not None and not _ws_is_closed(self._ws) and self._logged_in:
            return True
        async with self._lock:
            if self._ws is not None and not _ws_is_closed(self._ws) and self._logged_in:
                return True
            try:
                token = await self._rest_client.get_access_token()
            except Exception as e:
                logger.warning("Kiwoom WS 토큰 발급 실패: {}", str(e))
                return False
            try:
                self._ws = await websockets.connect(self._ws_url, ping_interval=None)
                await self._ws.send(json.dumps({"trnm": "LOGIN", "token": token}))
                raw = await asyncio.wait_for(self._ws.recv(), timeout=self.LOGIN_TIMEOUT_SEC)
                resp = json.loads(raw)
                if resp.get("trnm") == "LOGIN" and str(resp.get("return_code")) == "0":
                    self._logged_in = True
                    logger.debug("Kiwoom WebSocket LOGIN 성공 ({})", self._ws_url)
                    return True
                logger.warning("Kiwoom WS LOGIN 실패: {}", resp.get("return_msg"))
            except Exception as e:
                logger.warning("Kiwoom WS 연결 실패: {}", str(e))
            self._logged_in = False
            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass
                self._ws = None
            return False

    async def subscribe(self, symbol: str, market: str = "KRX") -> bool:
        symbol = normalize_krx_symbol(symbol)
        if not symbol:
            return False
        if symbol in self._subscriptions:
            return True
        if len(self._subscriptions) >= self.MAX_SUBSCRIPTIONS:
            logger.warning("Kiwoom WS 구독 한도 초과 (최대 {}종목)", self.MAX_SUBSCRIPTIONS)
            return False
        if not await self._ensure_connection():
            return False
        try:
            await self._ws.send(json.dumps({
                "trnm": "REG",
                "grp_no": "1",
                "refresh": "1",
                "data": [{"item": [symbol], "type": [self.REALTIME_TYPE]}],
            }))
            self._subscriptions.add(symbol)
            logger.debug("Kiwoom WS 종목 구독: {}", symbol)
            return True
        except Exception as e:
            logger.error("Kiwoom WS 구독 실패 {}: {}", symbol, str(e))
            return False

    async def unsubscribe(self, symbol: str, market: str = "KRX") -> None:
        symbol = normalize_krx_symbol(symbol)
        if symbol not in self._subscriptions:
            return
        if self._ws is not None and not _ws_is_closed(self._ws):
            try:
                await self._ws.send(json.dumps({
                    "trnm": "REMOVE",
                    "grp_no": "1",
                    "data": [{"item": [symbol], "type": [self.REALTIME_TYPE]}],
                }))
            except Exception:
                pass
        self._subscriptions.discard(symbol)
        logger.debug("Kiwoom WS 종목 구독 해제: {}", symbol)

    async def listen(self) -> None:
        """수신 루프. ws 가 닫히면 반환 → 상위(stream_manager)가 재연결한다."""
        if not await self._ensure_connection():
            await asyncio.sleep(5)
            return
        try:
            async for raw_msg in self._ws:
                if not self._running:
                    break
                await self._handle_message(raw_msg)
        except websockets.ConnectionClosed:
            logger.warning("Kiwoom WS 연결 끊김 → 재연결 대기")
        except Exception as e:
            logger.error("Kiwoom WS 수신 오류: {}", str(e))

    async def _handle_message(self, raw_msg: str) -> None:
        try:
            msg = json.loads(raw_msg)
        except Exception:
            return
        trnm = msg.get("trnm")
        if trnm == "PING":
            # 서버 PING 은 그대로 echo (keepalive)
            try:
                await self._ws.send(raw_msg)
            except Exception:
                pass
            return
        if trnm == "REAL":
            for item in msg.get("data", []) or []:
                price_data = self._parse_real(item)
                if price_data and self._on_price_callback:
                    await self._on_price_callback(price_data)

    def _parse_real(self, item: dict) -> dict | None:
        """REAL 0B(주식체결) → 표준 가격 dict. FID: 10현재가 11전일대비 12등락율 13누적거래량 15체결량."""
        if item.get("type") != self.REALTIME_TYPE:
            return None
        values = item.get("values", {}) or {}
        symbol = normalize_krx_symbol(item.get("item", ""))
        raw_price = values.get("10")
        if not symbol or raw_price in (None, ""):
            return None

        def _num(code: str, cast=float):
            v = values.get(code)
            if v in (None, ""):
                return 0
            try:
                return cast(str(v).replace("+", "").strip())
            except (TypeError, ValueError):
                return 0

        try:
            # 현재가는 +/- 부호가 붙을 수 있어 절대값으로 처리한다.
            price = abs(float(str(raw_price).replace("+", "").replace("-", "").strip()))
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        return {
            "market": "KRX",
            "symbol": symbol,
            "price": price,
            "change": _num("11"),
            "change_rate": _num("12"),
            "volume": _num("15", int),
            "cumulative_volume": _num("13", int),
        }

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)

    @property
    def is_connected(self) -> bool:
        return bool(self._ws is not None and not _ws_is_closed(self._ws) and self._logged_in)


# 싱글톤
kiwoom_websocket = KiwoomWebSocket()
