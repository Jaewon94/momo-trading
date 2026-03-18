"""거래 관련 Pydantic 모델 (API 통신용, DB 모델 아님)"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, model_validator

from trading.enums import Market, OrderSide, OrderType


class KISTokenInfo(BaseModel):
    """KIS API 토큰 정보"""
    access_token: str
    token_type: str
    expires_at: datetime


class MCPRequest(BaseModel):
    """MCP 서버 요청"""
    tool_name: str
    arguments: dict


class MCPResponse(BaseModel):
    """MCP 서버 응답"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


class CurrentPrice(BaseModel):
    """현재가 정보"""
    symbol: str
    market: Market
    price: float
    change: float
    change_rate: float
    volume: int
    timestamp: datetime


class Candle(BaseModel):
    """정규화된 캔들 데이터"""
    time_key: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class BrokerCapabilities(BaseModel):
    """브로커 기능 매트릭스"""
    supports_domestic_stocks: bool = False
    supports_overseas_stocks: bool = False
    supports_paper_trading: bool = False
    supports_live_trading: bool = False
    supports_realtime_quotes: bool = False
    supports_order_cancellation: bool = False


class OrderRequest(BaseModel):
    """주문 요청"""
    symbol: str
    market: Market
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[float] = None  # 시장가 주문 시 None

    @model_validator(mode="after")
    def validate_order_request(self) -> "OrderRequest":
        if self.quantity <= 0:
            raise ValueError("주문 수량은 1 이상이어야 합니다")

        if self.order_type == OrderType.LIMIT:
            if self.price is None or self.price <= 0:
                raise ValueError("지정가 주문은 유효한 가격이 필요합니다")

        if self.order_type == OrderType.MARKET:
            self.price = None

        return self


class OrderResult(BaseModel):
    """주문 실행 결과"""
    success: bool
    order_id: Optional[str] = None
    message: str
    filled_quantity: int = 0
    filled_price: float = 0.0


class AccountBalance(BaseModel):
    """계좌 잔고"""
    total_asset: float
    cash: float
    stock_value: float
    total_pnl: float
    total_pnl_rate: float
    is_valid: bool = True  # False이면 조회 실패 상태


class HoldingInfo(BaseModel):
    """보유 종목 정보"""
    symbol: str
    name: str
    quantity: int
    avg_buy_price: float
    current_price: float
    pnl: float
    pnl_rate: float


class PendingOrderInfo(BaseModel):
    """미체결 주문 정보"""
    order_id: str           # odno (주문번호)
    symbol: str             # pdno (종목코드)
    name: str               # prdt_name (종목명)
    side: str               # 매수/매도
    order_qty: int          # 주문수량
    filled_qty: int         # 체결수량
    remaining_qty: int      # 미체결수량
    order_price: float      # 주문단가
    order_time: str         # 주문시각
