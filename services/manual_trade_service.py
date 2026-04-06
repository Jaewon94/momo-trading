"""관리자 수동 거래 액션 서비스"""

from agent.decision_maker import decision_maker
from core.config import settings
from exceptions.common import ServiceException
from services.activity_logger import activity_logger
from trading.adapters.base import BrokerAdapter
from trading.broker_factory import get_broker_adapter
from trading.enums import ActivityPhase, ActivityType, Market, OrderSide, OrderType
from trading.models import HoldingInfo, OrderRequest, OrderResult, PendingOrderInfo
from trading.symbols import normalize_krx_symbol


class ManualTradeService:
    """보유 종목 즉시 매도와 미체결 주문 후속 액션"""

    def __init__(self, broker_adapter: BrokerAdapter | None = None) -> None:
        self._broker_adapter = broker_adapter

    @property
    def broker_adapter(self) -> BrokerAdapter:
        return self._broker_adapter or get_broker_adapter()

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return normalize_krx_symbol(symbol)

    async def _ensure_trading_enabled(self) -> None:
        if not settings.TRADING_ENABLED:
            raise ServiceException.bad_request("실주문이 비활성화되어 있습니다 (TRADING_ENABLED=false)")

    async def _get_holdings(self) -> list[HoldingInfo]:
        return list(await self.broker_adapter.get_holdings())

    async def _get_pending_orders(self) -> list[PendingOrderInfo]:
        return list(await self.broker_adapter.get_pending_orders())

    async def _find_holding(self, symbol: str) -> HoldingInfo:
        normalized_symbol = self._normalize_symbol(symbol)
        for holding in await self._get_holdings():
            if self._normalize_symbol(getattr(holding, "symbol", "")) == normalized_symbol:
                return holding
        raise ServiceException.bad_request("보유 수량이 없어 즉시 매도할 수 없습니다")

    async def _find_pending_order(self, order_id: str) -> PendingOrderInfo:
        for order in await self._get_pending_orders():
            if str(getattr(order, "order_id", "")) == str(order_id):
                return order
        raise ServiceException.not_found("대상 미체결 주문을 찾을 수 없습니다")

    async def _place_market_sell(self, holding: HoldingInfo) -> OrderResult:
        symbol = self._normalize_symbol(getattr(holding, "symbol", ""))
        quantity = int(getattr(holding, "quantity", 0) or 0)
        if quantity <= 0:
            raise ServiceException.bad_request("보유 수량이 없어 즉시 매도할 수 없습니다")

        return await self.broker_adapter.place_order(
            OrderRequest(
                symbol=symbol,
                market=Market.KRX,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=quantity,
            )
        )

    async def sell_position(self, symbol: str) -> dict:
        await self._ensure_trading_enabled()
        normalized_symbol = self._normalize_symbol(symbol)
        holding = await self._find_holding(normalized_symbol)
        pending_orders = await self._get_pending_orders()
        pending_sell = next(
            (
                order for order in pending_orders
                if self._normalize_symbol(getattr(order, "symbol", "")) == normalized_symbol
                and str(getattr(order, "side", "")) == "매도"
            ),
            None,
        )
        if pending_sell:
            raise ServiceException.conflict("이미 같은 종목의 매도 주문이 대기 중입니다")

        result = await self._place_market_sell(holding)
        if not result.success or not result.order_id:
            message = result.message or "즉시 매도 주문 접수 실패"
            await activity_logger.log(
                ActivityType.ORDER,
                ActivityPhase.ERROR,
                f"❌ [{normalized_symbol}] 수동 즉시 매도 실패: {message}",
                symbol=normalized_symbol,
                error_message=message,
            )
            raise ServiceException.bad_request(message)

        quantity = int(getattr(holding, "quantity", 0) or 0)
        expected_price = float(getattr(holding, "current_price", 0.0) or 0.0)
        await activity_logger.log(
            ActivityType.ORDER,
            ActivityPhase.COMPLETE,
            f"🖱 [{normalized_symbol}] 수동 즉시 매도 주문 접수 — {quantity}주",
            symbol=normalized_symbol,
            detail={
                "action": "MANUAL_SELL",
                "order_id": result.order_id,
                "quantity": quantity,
                "order_type": "MARKET",
            },
        )
        await decision_maker.confirm_and_record(
            symbol=normalized_symbol,
            side="SELL",
            order_id=result.order_id,
            quantity=quantity,
            expected_price=expected_price,
            analysis_context={
                "stock_name": getattr(holding, "name", normalized_symbol),
                "strategy_type": "MANUAL",
                "ai_recommendation": "SELL",
                "entry_pattern": "MANUAL_SELL",
            },
            exit_reason="MANUAL_SELL",
        )
        self.broker_adapter.invalidate_cache()
        return {
            "symbol": normalized_symbol,
            "name": getattr(holding, "name", normalized_symbol),
            "quantity": quantity,
            "order_id": result.order_id,
            "message": "즉시 매도 주문 접수",
        }

    async def cancel_pending_buy(self, order_id: str) -> dict:
        await self._ensure_trading_enabled()
        order = await self._find_pending_order(order_id)
        if str(getattr(order, "side", "")) != "매수":
            raise ServiceException.bad_request("미체결 매수 주문만 취소할 수 있습니다")

        result = await self.broker_adapter.cancel_order(str(order_id), market=Market.KRX)
        if not result.success:
            message = result.message or "미체결 매수 주문 취소 실패"
            await activity_logger.log(
                ActivityType.ORDER,
                ActivityPhase.ERROR,
                f"❌ [{self._normalize_symbol(order.symbol)}] 미체결 매수 주문 취소 실패: {message}",
                symbol=self._normalize_symbol(order.symbol),
                error_message=message,
            )
            raise ServiceException.bad_request(message)

        self.broker_adapter.invalidate_cache()
        await activity_logger.log(
            ActivityType.ORDER,
            ActivityPhase.COMPLETE,
            f"🧹 [{self._normalize_symbol(order.symbol)}] 미체결 매수 주문 취소 — 주문번호: {order_id}",
            symbol=self._normalize_symbol(order.symbol),
            detail={
                "action": "CANCEL_PENDING_BUY",
                "order_id": str(order_id),
                "side": "BUY",
            },
        )
        return {
            "order_id": str(order_id),
            "symbol": self._normalize_symbol(order.symbol),
            "name": getattr(order, "name", self._normalize_symbol(order.symbol)),
            "message": "미체결 매수 주문 취소 완료",
        }

    async def replace_pending_sell_with_market_order(self, order_id: str) -> dict:
        await self._ensure_trading_enabled()
        order = await self._find_pending_order(order_id)
        if str(getattr(order, "side", "")) != "매도":
            raise ServiceException.bad_request("미체결 매도 주문만 재매도할 수 있습니다")

        holding = await self._find_holding(order.symbol)
        cancel_result = await self.broker_adapter.cancel_order(str(order_id), market=Market.KRX)
        if not cancel_result.success:
            message = cancel_result.message or "기존 매도 주문 취소 실패"
            await activity_logger.log(
                ActivityType.ORDER,
                ActivityPhase.ERROR,
                f"❌ [{self._normalize_symbol(order.symbol)}] 기존 매도 주문 취소 실패: {message}",
                symbol=self._normalize_symbol(order.symbol),
                error_message=message,
            )
            raise ServiceException.bad_request(message)

        await activity_logger.log(
            ActivityType.ORDER,
            ActivityPhase.COMPLETE,
            f"🧹 [{self._normalize_symbol(order.symbol)}] 기존 매도 주문 취소 — 주문번호: {order_id}",
            symbol=self._normalize_symbol(order.symbol),
            detail={
                "action": "CANCEL_PENDING_SELL",
                "order_id": str(order_id),
                "side": "SELL",
            },
        )

        result = await self._place_market_sell(holding)
        if not result.success or not result.order_id:
            message = result.message or "시장가 재매도 주문 접수 실패"
            await activity_logger.log(
                ActivityType.ORDER,
                ActivityPhase.ERROR,
                f"❌ [{self._normalize_symbol(order.symbol)}] 취소 후 즉시 매도 실패: {message}",
                symbol=self._normalize_symbol(order.symbol),
                error_message=message,
            )
            raise ServiceException.internal_server_error(
                f"기존 매도 주문은 취소되었지만 새 매도 주문 접수에 실패했습니다: {message}"
            )

        quantity = int(getattr(holding, "quantity", 0) or 0)
        expected_price = float(getattr(holding, "current_price", 0.0) or 0.0)
        await activity_logger.log(
            ActivityType.ORDER,
            ActivityPhase.COMPLETE,
            f"🖱 [{self._normalize_symbol(order.symbol)}] 취소 후 즉시 매도 재접수 — {quantity}주",
            symbol=self._normalize_symbol(order.symbol),
            detail={
                "action": "CANCEL_AND_SELL",
                "cancelled_order_id": str(order_id),
                "new_order_id": result.order_id,
                "quantity": quantity,
                "order_type": "MARKET",
            },
        )
        await decision_maker.confirm_and_record(
            symbol=self._normalize_symbol(order.symbol),
            side="SELL",
            order_id=result.order_id,
            quantity=quantity,
            expected_price=expected_price,
            analysis_context={
                "stock_name": getattr(holding, "name", self._normalize_symbol(order.symbol)),
                "strategy_type": "MANUAL",
                "ai_recommendation": "SELL",
                "entry_pattern": "CANCEL_AND_SELL",
            },
            exit_reason="MANUAL_REPLACE_SELL",
        )
        self.broker_adapter.invalidate_cache()
        return {
            "symbol": self._normalize_symbol(order.symbol),
            "name": getattr(order, "name", self._normalize_symbol(order.symbol)),
            "quantity": quantity,
            "cancelled_order_id": str(order_id),
            "new_order_id": result.order_id,
            "message": "기존 매도 주문 취소 후 시장가 매도 재접수",
        }


manual_trade_service = ManualTradeService()
