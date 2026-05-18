"""Read-only reconciliation between SELL executions and BUY close lots."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade_result import TradeResult
from trading.symbols import normalize_krx_symbol


REPAIRED_FROM_SELL_ORDER_PATTERN = re.compile(r"repaired from broker-confirmed sell order\s+([A-Za-z0-9_-]+)")


@dataclass
class _BuyCandidate:
    row: TradeResult
    remaining_qty: int


@dataclass
class _SellReflectionFilterResult:
    sells: list[TradeResult]
    reflected_count: int
    reflected_quantity: int


class TradeCloseReconciliationService:
    """Builds a dry-run plan for repairing SELL rows that did not close BUY lots."""

    async def build_dry_run(
        self,
        session: AsyncSession,
        *,
        days: int = 30,
    ) -> dict:
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=max(int(days), 1))
        raw_sells = await self._fetch_sell_executions(session, from_dt=from_dt, to_dt=to_dt)
        reflected_buy_closes = await self._fetch_reflected_buy_closes(session, from_dt=from_dt, to_dt=to_dt)
        reflection_filter = self._filter_already_reflected_sells(raw_sells, reflected_buy_closes)
        sells = reflection_filter.sells
        buy_candidates = await self._fetch_buy_candidates(session, from_dt=from_dt, to_dt=to_dt)

        grouped_buys: dict[str, list[_BuyCandidate]] = {}
        for row in buy_candidates:
            symbol = normalize_krx_symbol(getattr(row, "stock_symbol", ""))
            grouped_buys.setdefault(symbol, []).append(_BuyCandidate(
                row=row,
                remaining_qty=max(int(getattr(row, "quantity", 0) or 0), 0),
            ))

        matches = []
        unmatched_sells = []
        total_matched_qty = 0
        total_unmatched_sell_qty = 0
        total_estimated_pnl = 0.0

        for sell in sells:
            sell_symbol = normalize_krx_symbol(getattr(sell, "stock_symbol", ""))
            sell_qty = max(int(getattr(sell, "quantity", 0) or 0), 0)
            sell_price = float(getattr(sell, "exit_price", 0.0) or 0.0)
            sell_at = getattr(sell, "exit_at", None) or getattr(sell, "entry_at", None)
            remaining_sell_qty = sell_qty
            sell_matches = []

            for candidate in grouped_buys.get(sell_symbol, []):
                if remaining_sell_qty <= 0:
                    break
                if candidate.remaining_qty <= 0:
                    continue
                buy_at = getattr(candidate.row, "entry_at", None)
                if buy_at and sell_at and buy_at > sell_at:
                    continue

                close_qty = min(candidate.remaining_qty, remaining_sell_qty)
                entry_price = float(getattr(candidate.row, "entry_price", 0.0) or 0.0)
                estimated_pnl = (sell_price - entry_price) * close_qty
                estimated_return_pct = ((sell_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0
                sell_matches.append({
                    "buy_id": getattr(candidate.row, "id", None),
                    "buy_symbol": normalize_krx_symbol(getattr(candidate.row, "stock_symbol", "")),
                    "buy_entry_at": buy_at.isoformat() if buy_at else None,
                    "buy_entry_price": entry_price,
                    "close_quantity": close_qty,
                    "estimated_pnl": round(estimated_pnl, 2),
                    "estimated_return_pct": round(estimated_return_pct, 4),
                    "current_exit_reason": str(getattr(candidate.row, "exit_reason", "") or ""),
                    "current_exit_at": getattr(candidate.row, "exit_at", None).isoformat()
                    if getattr(candidate.row, "exit_at", None) else None,
                })
                candidate.remaining_qty -= close_qty
                remaining_sell_qty -= close_qty
                total_matched_qty += close_qty
                total_estimated_pnl += estimated_pnl

            item = {
                "sell_id": getattr(sell, "id", None),
                "sell_symbol_raw": str(getattr(sell, "stock_symbol", "") or ""),
                "sell_symbol": sell_symbol,
                "sell_exit_at": sell_at.isoformat() if sell_at else None,
                "sell_price": sell_price,
                "sell_quantity": sell_qty,
                "matched_quantity": sell_qty - remaining_sell_qty,
                "unmatched_quantity": remaining_sell_qty,
                "estimated_pnl": round(sum(float(match["estimated_pnl"]) for match in sell_matches), 2),
                "matches": sell_matches,
            }
            if sell_matches:
                matches.append(item)
            if remaining_sell_qty > 0:
                total_unmatched_sell_qty += remaining_sell_qty
                unmatched_sells.append(item)

        remaining_buy_candidates = []
        for symbol, candidates in grouped_buys.items():
            for candidate in candidates:
                if candidate.remaining_qty <= 0:
                    continue
                row = candidate.row
                remaining_buy_candidates.append({
                    "buy_id": getattr(row, "id", None),
                    "symbol": symbol,
                    "stock_name": str(getattr(row, "stock_name", "") or symbol),
                    "entry_at": getattr(row, "entry_at", None).isoformat() if getattr(row, "entry_at", None) else None,
                    "entry_price": float(getattr(row, "entry_price", 0.0) or 0.0),
                    "remaining_quantity": candidate.remaining_qty,
                    "current_exit_reason": str(getattr(row, "exit_reason", "") or ""),
                })

        return {
            "mode": "DRY_RUN",
            "window": {
                "from": from_dt.isoformat(),
                "to": to_dt.isoformat(),
                "days": max(int(days), 1),
            },
            "summary": {
                "raw_sell_execution_count": len(raw_sells),
                "sell_execution_count": len(sells),
                "reflected_sell_count": reflection_filter.reflected_count,
                "reflected_sell_quantity": reflection_filter.reflected_quantity,
                "buy_candidate_count": len(buy_candidates),
                "matched_sell_count": len(matches),
                "unmatched_sell_count": len(unmatched_sells),
                "matched_quantity": total_matched_qty,
                "unmatched_sell_quantity": total_unmatched_sell_qty,
                "remaining_buy_candidate_count": len(remaining_buy_candidates),
                "estimated_pnl": round(total_estimated_pnl, 2),
            },
            "matches": matches,
            "unmatched_sells": unmatched_sells,
            "remaining_buy_candidates": remaining_buy_candidates,
        }

    async def apply_reconciliation(
        self,
        session: AsyncSession,
        *,
        days: int = 30,
        apply_unmatched_sells: bool = False,
    ) -> dict:
        """Apply the dry-run plan to BUY lots.

        By default, only SELL rows with fully matched quantity are applied. Partial
        SELL matches are left for manual review because their missing quantity
        could represent a broker-side lot not present in the local DB.
        """
        dry_run = await self.build_dry_run(session, days=days)
        applied = []
        skipped = []
        updated_buy_lots = 0
        created_buy_lots = 0
        total_applied_qty = 0
        total_applied_pnl = 0.0

        for sell_match in dry_run["matches"]:
            unmatched_qty = int(sell_match.get("unmatched_quantity") or 0)
            if unmatched_qty > 0 and not apply_unmatched_sells:
                skipped.append({**sell_match, "reason": "sell_has_unmatched_quantity"})
                continue

            sell = await session.get(TradeResult, sell_match.get("sell_id"))
            if sell is None:
                skipped.append({**sell_match, "reason": "sell_row_missing"})
                continue
            if "CLOSE_RECONCILIATION_APPLY" in str(getattr(sell, "notes", "") or ""):
                skipped.append({**sell_match, "reason": "sell_already_applied"})
                continue

            sell_at = getattr(sell, "exit_at", None) or getattr(sell, "entry_at", None)
            sell_price = float(getattr(sell, "exit_price", 0.0) or 0.0)
            sell_applied_qty = 0
            sell_applied_pnl = 0.0
            sell_applied_lots = []

            for buy_match in sell_match.get("matches") or []:
                buy = await session.get(TradeResult, buy_match.get("buy_id"))
                if buy is None:
                    skipped.append({**buy_match, "sell_id": sell_match.get("sell_id"), "reason": "buy_row_missing"})
                    continue
                if "CLOSE_RECONCILIATION_APPLY" in str(getattr(buy, "notes", "") or ""):
                    skipped.append({**buy_match, "sell_id": sell_match.get("sell_id"), "reason": "buy_already_applied"})
                    continue

                close_qty = max(int(buy_match.get("close_quantity") or 0), 0)
                lot_qty = max(int(getattr(buy, "quantity", 0) or 0), 0)
                if close_qty <= 0 or lot_qty <= 0:
                    skipped.append({**buy_match, "sell_id": sell_match.get("sell_id"), "reason": "invalid_quantity"})
                    continue

                target = buy
                if close_qty < lot_qty:
                    target = self._clone_buy_for_close(buy, close_qty=close_qty)
                    session.add(target)
                    await session.flush()
                    buy.quantity = lot_qty - close_qty
                    buy.notes = self._append_note(
                        getattr(buy, "notes", None),
                        f"CLOSE_RECONCILIATION_SPLIT_REMAINING: sell_id={sell_match.get('sell_id')}",
                    )
                    created_buy_lots += 1

                entry_price = float(getattr(target, "entry_price", 0.0) or 0.0)
                pnl = (sell_price - entry_price) * close_qty
                return_pct = ((sell_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0
                target.quantity = close_qty
                target.exit_price = sell_price
                target.pnl = round(pnl, 2)
                target.return_pct = round(return_pct, 4)
                target.is_win = pnl > 0
                target.exit_reason = str(getattr(sell, "exit_reason", "") or "SELL_RECONCILIATION")
                target.exit_at = sell_at
                target.hold_days = self._hold_days(getattr(target, "entry_at", None), sell_at)
                target.notes = self._append_note(
                    getattr(target, "notes", None),
                    f"CLOSE_RECONCILIATION_APPLY: sell_id={sell_match.get('sell_id')}",
                )

                updated_buy_lots += 1
                sell_applied_qty += close_qty
                sell_applied_pnl += pnl
                sell_applied_lots.append({
                    "buy_id": getattr(target, "id", None),
                    "close_quantity": close_qty,
                    "pnl": round(pnl, 2),
                    "return_pct": round(return_pct, 4),
                })

            if sell_applied_qty <= 0:
                skipped.append({**sell_match, "reason": "no_buy_lots_applied"})
                continue

            sell.pnl = round(sell_applied_pnl, 2)
            sell.return_pct = 0.0
            sell.notes = self._append_note(
                getattr(sell, "notes", None),
                f"CLOSE_RECONCILIATION_APPLY: matched_qty={sell_applied_qty}",
            )
            applied.append({
                "sell_id": sell_match.get("sell_id"),
                "sell_symbol": sell_match.get("sell_symbol"),
                "matched_quantity": sell_applied_qty,
                "applied_lot_count": len(sell_applied_lots),
                "estimated_pnl": round(sell_applied_pnl, 2),
                "lots": sell_applied_lots,
            })
            total_applied_qty += sell_applied_qty
            total_applied_pnl += sell_applied_pnl

        return {
            "mode": "APPLY",
            "window": dry_run["window"],
            "summary": {
                "dry_run_sell_execution_count": dry_run["summary"]["sell_execution_count"],
                "eligible_full_match_sell_count": sum(
                    1 for item in dry_run["matches"] if int(item.get("unmatched_quantity") or 0) == 0
                ),
                "applied_sell_count": len(applied),
                "updated_buy_lot_count": updated_buy_lots,
                "created_buy_lot_count": created_buy_lots,
                "skipped_count": len(skipped),
                "applied_quantity": total_applied_qty,
                "applied_pnl": round(total_applied_pnl, 2),
            },
            "applied": applied,
            "skipped": skipped,
            "dry_run_summary": dry_run["summary"],
        }

    async def _fetch_sell_executions(
        self,
        session: AsyncSession,
        *,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[TradeResult]:
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "SELL",
                TradeResult.status == "CONFIRMED",
                TradeResult.exit_at.isnot(None),
                TradeResult.exit_at >= from_dt,
                TradeResult.exit_at <= to_dt,
                or_(
                    TradeResult.notes.is_(None),
                    ~TradeResult.notes.like("%CLOSE_RECONCILIATION_APPLY%"),
                ),
            ))
            .order_by(TradeResult.exit_at.asc(), TradeResult.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    async def _fetch_reflected_buy_closes(
        self,
        session: AsyncSession,
        *,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[TradeResult]:
        """Fetch BUY lots already closed by the live SELL confirmation path.

        Neutral holding reconciliation closes stay out of this set because those
        rows are intentionally candidates for later SELL-to-BUY reconciliation.
        """
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.status == "CONFIRMED",
                TradeResult.exit_at.isnot(None),
                TradeResult.exit_at >= from_dt,
                TradeResult.exit_at <= to_dt,
                or_(
                    TradeResult.notes.is_(None),
                    ~TradeResult.notes.like("%HOLDING_RECONCILIATION_CLOSE%"),
                ),
            ))
            .order_by(TradeResult.exit_at.asc(), TradeResult.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    async def _fetch_buy_candidates(
        self,
        session: AsyncSession,
        *,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[TradeResult]:
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.status == "CONFIRMED",
                TradeResult.entry_at.isnot(None),
                TradeResult.entry_at >= from_dt,
                TradeResult.entry_at <= to_dt,
                or_(
                    TradeResult.exit_at.is_(None),
                    TradeResult.notes.like("HOLDING_RECONCILIATION_CLOSE%"),
                ),
                or_(
                    TradeResult.notes.is_(None),
                    ~TradeResult.notes.like("%CLOSE_RECONCILIATION_APPLY%"),
                ),
            ))
            .order_by(TradeResult.stock_symbol.asc(), TradeResult.entry_at.asc(), TradeResult.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    @classmethod
    def _filter_already_reflected_sells(
        cls,
        sells: list[TradeResult],
        reflected_buy_closes: list[TradeResult],
    ) -> _SellReflectionFilterResult:
        reflected_qty_by_key: dict[tuple[str, datetime, float, str], int] = {}
        reflected_qty_by_order_id: dict[str, int] = {}
        for buy in reflected_buy_closes:
            key = cls._reflection_key(buy)
            buy_qty = max(int(getattr(buy, "quantity", 0) or 0), 0)
            if key is None:
                order_id = cls._repaired_sell_order_id(buy)
                if order_id:
                    reflected_qty_by_order_id[order_id] = reflected_qty_by_order_id.get(order_id, 0) + buy_qty
                continue
            reflected_qty_by_key[key] = reflected_qty_by_key.get(key, 0) + buy_qty
            order_id = cls._repaired_sell_order_id(buy)
            if order_id:
                reflected_qty_by_order_id[order_id] = reflected_qty_by_order_id.get(order_id, 0) + buy_qty

        actionable_sells: list[TradeResult] = []
        reflected_count = 0
        reflected_quantity = 0
        for sell in sells:
            sell_qty = max(int(getattr(sell, "quantity", 0) or 0), 0)
            key = cls._reflection_key(sell)
            order_id = str(getattr(sell, "order_id", "") or "")
            key_qty = reflected_qty_by_key.get(key, 0) if key is not None else 0
            order_qty = reflected_qty_by_order_id.get(order_id, 0) if order_id else 0
            if sell_qty > 0 and key_qty + order_qty >= sell_qty:
                remaining = sell_qty
                if key is not None:
                    used_key_qty = min(reflected_qty_by_key.get(key, 0), remaining)
                    reflected_qty_by_key[key] = reflected_qty_by_key.get(key, 0) - used_key_qty
                    remaining -= used_key_qty
                if order_id and remaining > 0:
                    reflected_qty_by_order_id[order_id] = reflected_qty_by_order_id.get(order_id, 0) - remaining
                reflected_count += 1
                reflected_quantity += sell_qty
                continue
            actionable_sells.append(sell)

        return _SellReflectionFilterResult(
            sells=actionable_sells,
            reflected_count=reflected_count,
            reflected_quantity=reflected_quantity,
        )

    @staticmethod
    def _reflection_key(row: TradeResult) -> tuple[str, datetime, float, str] | None:
        exit_at = getattr(row, "exit_at", None)
        if not isinstance(exit_at, datetime):
            return None
        symbol = normalize_krx_symbol(getattr(row, "stock_symbol", ""))
        if not symbol:
            return None
        price = round(float(getattr(row, "exit_price", 0.0) or 0.0), 6)
        reason = str(getattr(row, "exit_reason", "") or "")
        return (symbol, exit_at, price, reason)

    @staticmethod
    def _repaired_sell_order_id(row: TradeResult) -> str:
        notes = str(getattr(row, "notes", "") or "")
        match = REPAIRED_FROM_SELL_ORDER_PATTERN.search(notes)
        return match.group(1) if match else ""

    @staticmethod
    def _clone_buy_for_close(source: TradeResult, *, close_qty: int) -> TradeResult:
        return TradeResult(
            order_id=None,
            stock_symbol=str(getattr(source, "stock_symbol", "") or ""),
            stock_name=str(getattr(source, "stock_name", "") or ""),
            side="BUY",
            strategy_type=str(getattr(source, "strategy_type", "") or ""),
            entry_price=float(getattr(source, "entry_price", 0.0) or 0.0),
            exit_price=0.0,
            quantity=int(close_qty),
            pnl=0.0,
            return_pct=0.0,
            is_win=False,
            hold_days=0,
            exit_reason="",
            ai_recommendation=str(getattr(source, "ai_recommendation", "") or ""),
            ai_confidence=float(getattr(source, "ai_confidence", 0.0) or 0.0),
            ai_target_price=getattr(source, "ai_target_price", None),
            ai_stop_loss_price=getattr(source, "ai_stop_loss_price", None),
            entry_rsi=getattr(source, "entry_rsi", None),
            entry_macd_hist=getattr(source, "entry_macd_hist", None),
            entry_bb_position=getattr(source, "entry_bb_position", None),
            entry_pattern=getattr(source, "entry_pattern", None),
            market=str(getattr(source, "market", "KRX") or "KRX"),
            market_regime=str(getattr(source, "market_regime", "") or ""),
            notes=getattr(source, "notes", None),
            status=str(getattr(source, "status", "CONFIRMED") or "CONFIRMED"),
            entry_at=getattr(source, "entry_at", None),
        )

    @staticmethod
    def _append_note(previous_note: str | None, note: str) -> str:
        previous = str(previous_note or "").strip()
        if note in previous:
            return previous
        if not previous:
            return note
        return f"{note} | previous={previous[:300]}"

    @staticmethod
    def _hold_days(entry_at, exit_at) -> int:
        if not entry_at or not exit_at:
            return 0
        comparable_exit = exit_at
        if getattr(entry_at, "tzinfo", None) is None and getattr(exit_at, "tzinfo", None) is not None:
            comparable_exit = exit_at.replace(tzinfo=None)
        return max((comparable_exit - entry_at).days, 0)


trade_close_reconciliation_service = TradeCloseReconciliationService()
