"""매매 총괄 서비스 - 브로커 어댑터를 통한 주문 실행 + 계좌 조회"""
from core.config import settings
from exceptions.common import ServiceException
from trading.adapters.base import BrokerAdapter
from trading.broker_factory import get_broker_adapter
from trading.enums import Market
from trading.models import AccountBalance, OrderRequest, OrderResult


class TradingService:
    """매매 총괄 서비스"""

    def __init__(self, broker_adapter: BrokerAdapter | None = None):
        self._broker_adapter = broker_adapter or get_broker_adapter()

    async def check_trading_enabled(self) -> None:
        if not settings.TRADING_ENABLED:
            raise ServiceException.bad_request("매매가 비활성화되어 있습니다 (TRADING_ENABLED=false)")

    async def get_account_balance(self) -> AccountBalance:
        """계좌 잔고 조회"""
        return await self._broker_adapter.get_balance()

    async def execute_order(self, request: OrderRequest) -> OrderResult:
        await self.check_trading_enabled()

        # 주문 금액 한도는 AI 리스크 매니저가 사전 검증 (시스템 하드 리밋 없음)
        return await self._broker_adapter.place_order(request)

    async def get_current_price(self, symbol: str, market: str = "KRX") -> dict:
        try:
            quote = await self._broker_adapter.get_current_price(symbol, market=Market(market))
        except ValueError as exc:
            raise ServiceException.bad_request(f"지원하지 않는 시장입니다: {market}") from exc
        except RuntimeError as exc:
            raise ServiceException.internal_server_error(f"현재가 조회 실패: {exc}") from exc

        return quote.model_dump(mode="json")
