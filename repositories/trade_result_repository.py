"""매매 결과 리포지토리"""
from datetime import date, datetime, time

from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade_result import TradeResult
from repositories.async_base_repository import AsyncBaseRepository
from trading.symbols import normalize_krx_symbol
from util.time_util import KST


class TradeResultRepository(AsyncBaseRepository[TradeResult]):
    NEUTRAL_RECONCILIATION_EXIT_REASONS = frozenset({
        "BROKER_HOLDING_MISSING",
    })

    def __init__(self, session: AsyncSession):
        super().__init__(TradeResult, session)

    async def get_by_symbol(self, symbol: str, limit: int = 50) -> list[TradeResult]:
        normalized_symbol = normalize_krx_symbol(symbol)
        stmt = (
            select(TradeResult)
            .where(TradeResult.stock_symbol == normalized_symbol)
            .order_by(TradeResult.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_strategy(self, strategy_type: str, limit: int = 100) -> list[TradeResult]:
        stmt = (
            select(TradeResult)
            .where(TradeResult.strategy_type == strategy_type)
            .order_by(TradeResult.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, limit: int = 50) -> list[TradeResult]:
        stmt = (
            select(TradeResult)
            .order_by(TradeResult.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_open_buy(self, symbol: str) -> TradeResult | None:
        """미청산 매수 기록 조회 (exit_at IS NULL, side=BUY, status=CONFIRMED)"""
        normalized_symbol = normalize_krx_symbol(symbol)
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.stock_symbol == normalized_symbol,
                TradeResult.side == "BUY",
                TradeResult.exit_at.is_(None),
                TradeResult.status == "CONFIRMED",
            ))
            .order_by(TradeResult.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_open_buys(self, symbol: str) -> list[TradeResult]:
        """특정 종목의 미청산 BUY 전체 조회 (SELL 시 일괄 청산용)"""
        normalized_symbol = normalize_krx_symbol(symbol)
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.stock_symbol == normalized_symbol,
                TradeResult.side == "BUY",
                TradeResult.exit_at.is_(None),
                TradeResult.status == "CONFIRMED",
            ))
            .order_by(TradeResult.entry_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_completed_by_date(self, target_date: date) -> list[TradeResult]:
        """특정 날짜에 청산 완료된 포지션 (BUY→청산 기록만, CONFIRMED)

        SELL 레코드가 아닌, 청산된 BUY 레코드를 반환.
        이 레코드에 pnl, return_pct, is_win이 정확히 기록되어 있음.
        브로커 보유 대사 과정에서 만든 중립 복구 청산은 실제 실현손익이 아니므로 제외.
        """
        start = datetime.combine(target_date, time.min, tzinfo=KST)
        end = datetime.combine(target_date, time.max, tzinfo=KST)
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.exit_at.isnot(None),
                TradeResult.exit_at >= start,
                TradeResult.exit_at <= end,
                TradeResult.status == "CONFIRMED",
                self._is_not_neutral_reconciliation_close(),
            ))
            .order_by(TradeResult.exit_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    def _is_not_neutral_reconciliation_close(cls):
        return or_(
            TradeResult.notes.like("%CLOSE_RECONCILIATION_APPLY%"),
            and_(
                or_(
                    TradeResult.exit_reason.is_(None),
                    TradeResult.exit_reason.notin_(cls.NEUTRAL_RECONCILIATION_EXIT_REASONS),
                ),
                or_(
                    TradeResult.notes.is_(None),
                    ~TradeResult.notes.like("%HOLDING_RECONCILIATION_CLOSE%"),
                ),
            ),
        )

    async def get_sell_count_by_date(self, target_date: date) -> int:
        """특정 날짜의 매도 주문 건수 (SELL 레코드 수, CONFIRMED)"""
        start = datetime.combine(target_date, time.min, tzinfo=KST)
        end = datetime.combine(target_date, time.max, tzinfo=KST)
        stmt = (
            select(func.count())
            .select_from(TradeResult)
            .where(and_(
                TradeResult.side == "SELL",
                TradeResult.exit_at.isnot(None),
                TradeResult.exit_at >= start,
                TradeResult.exit_at <= end,
                TradeResult.status == "CONFIRMED",
            ))
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_sell_executions_by_date(self, target_date: date) -> list[TradeResult]:
        """특정 날짜의 매도 체결 기록 (SELL 레코드, CONFIRMED)"""
        start = datetime.combine(target_date, time.min, tzinfo=KST)
        end = datetime.combine(target_date, time.max, tzinfo=KST)
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "SELL",
                TradeResult.exit_at.isnot(None),
                TradeResult.exit_at >= start,
                TradeResult.exit_at <= end,
                TradeResult.status == "CONFIRMED",
            ))
            .order_by(TradeResult.exit_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_opened_by_date(self, target_date: date) -> list[TradeResult]:
        """특정 날짜에 진입한 매수 기록 (entry_at 기준, CONFIRMED만)

        브로커 보유 대사 과정에서 만든 중립 복구 청산은 운영 감사용 기록이라
        오늘 진입 목록에서도 제외한다.
        """
        start = datetime.combine(target_date, time.min, tzinfo=KST)
        end = datetime.combine(target_date, time.max, tzinfo=KST)
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.entry_at >= start,
                TradeResult.entry_at <= end,
                TradeResult.status == "CONFIRMED",
                self._is_not_neutral_reconciliation_close(),
            ))
            .order_by(TradeResult.entry_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_confirms_by_date(self, target_date: date) -> list[TradeResult]:
        """특정 날짜에 생성된 PENDING_CONFIRM 매수 기록"""
        start = datetime.combine(target_date, time.min, tzinfo=KST)
        end = datetime.combine(target_date, time.max, tzinfo=KST)
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.entry_at >= start,
                TradeResult.entry_at <= end,
                TradeResult.status == "PENDING_CONFIRM",
            ))
            .order_by(TradeResult.entry_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_all_open(self) -> list[TradeResult]:
        """미청산 포지션 전체 조회 (exit_at IS NULL, side=BUY, status=CONFIRMED)"""
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.exit_at.is_(None),
                TradeResult.status == "CONFIRMED",
            ))
            .order_by(TradeResult.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_order_id(self, order_id: str) -> TradeResult | None:
        """주문번호로 TradeResult 조회"""
        if not order_id:
            return None
        stmt = (
            select(TradeResult)
            .where(TradeResult.order_id == order_id)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_order_ids(self, order_ids: list[str]) -> list[TradeResult]:
        """주문번호 목록으로 TradeResult 조회"""
        normalized_ids = [str(order_id) for order_id in order_ids if str(order_id or "")]
        if not normalized_ids:
            return []
        stmt = (
            select(TradeResult)
            .where(TradeResult.order_id.in_(normalized_ids))
            .order_by(TradeResult.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_confirms(self) -> list[TradeResult]:
        """PENDING_CONFIRM 상태 레코드 조회 (복구용)"""
        stmt = (
            select(TradeResult)
            .where(TradeResult.status == "PENDING_CONFIRM")
            .order_by(TradeResult.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_buy_confirms(self, symbol: str | None = None) -> list[TradeResult]:
        """미확정 BUY 주문 조회.

        브로커 체결/미체결 조회가 지연되거나 누락될 때 같은 방향 주문이
        중복으로 쌓이지 않도록 주문 게이트에서 사용한다.
        """
        conditions = [
            TradeResult.side == "BUY",
            TradeResult.status == "PENDING_CONFIRM",
        ]
        if symbol:
            conditions.append(TradeResult.stock_symbol == normalize_krx_symbol(symbol))
        stmt = (
            select(TradeResult)
            .where(and_(*conditions))
            .order_by(TradeResult.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_confirmed_open_buys_with_zero_entry_price(self) -> list[TradeResult]:
        """미청산 CONFIRMED BUY 중 체결가가 0인 레코드 조회"""
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.exit_at.is_(None),
                TradeResult.status == "CONFIRMED",
                TradeResult.entry_price <= 0,
            ))
            .order_by(TradeResult.entry_at.asc(), TradeResult.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
