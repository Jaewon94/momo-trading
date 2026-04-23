"""Build a minimal domestic stock universe from broker-observed symbols."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.stock import Stock
from trading.broker_factory import get_broker_adapter
from trading.enums import Market
from trading.symbols import normalize_krx_symbol


@dataclass
class StockUniverseCandidate:
    symbol: str
    name: str
    market: str = Market.KRX.value
    category: str | None = None
    exchange_code: str | None = None
    sources: set[str] = field(default_factory=set)


class StockUniverseBootstrapService:
    async def process(
        self,
        session: AsyncSession,
        *,
        broker: Any | None = None,
        rank_limit: int = 50,
        apply: bool = False,
    ) -> dict[str, Any]:
        broker = broker or get_broker_adapter()
        candidates_by_symbol: dict[str, StockUniverseCandidate] = {}
        source_counts: dict[str, int] = {}

        await self._collect_objects(
            candidates_by_symbol,
            source_counts,
            "holdings",
            await self._safe_fetch(broker, "get_holdings"),
        )
        await self._collect_objects(
            candidates_by_symbol,
            source_counts,
            "pending_orders",
            await self._safe_fetch(broker, "get_pending_orders"),
        )
        await self._collect_rows(
            candidates_by_symbol,
            source_counts,
            "volume_rank",
            await self._safe_fetch(broker, "get_volume_rank"),
            limit=rank_limit,
        )
        await self._collect_rows(
            candidates_by_symbol,
            source_counts,
            "fluctuation_top",
            await self._safe_fetch(broker, "get_fluctuation_rank", "top"),
            limit=rank_limit,
        )
        await self._collect_rows(
            candidates_by_symbol,
            source_counts,
            "fluctuation_bottom",
            await self._safe_fetch(broker, "get_fluctuation_rank", "bottom"),
            limit=rank_limit,
        )

        candidates = sorted(candidates_by_symbol.values(), key=lambda item: item.symbol)
        existing = await self._load_existing(session, [item.symbol for item in candidates])

        created: list[StockUniverseCandidate] = []
        updated: list[StockUniverseCandidate] = []
        unchanged = 0
        for candidate in candidates:
            stock = existing.get(candidate.symbol)
            if stock is None:
                created.append(candidate)
                if apply:
                    session.add(Stock(
                        symbol=candidate.symbol,
                        name=candidate.name,
                        market=candidate.market,
                        category=candidate.category,
                        exchange_code=candidate.exchange_code,
                        is_active=True,
                    ))
                continue

            changes = self._stock_changes(stock, candidate)
            if not changes:
                unchanged += 1
                continue
            updated.append(candidate)
            if apply:
                for key, value in changes.items():
                    setattr(stock, key, value)
                session.add(stock)

        if apply:
            await session.flush()

        logger.info(
            "stocks universe bootstrap {}: 후보 {}건 / 생성 {}건 / 갱신 {}건 / 유지 {}건",
            "적용" if apply else "DRY_RUN",
            len(candidates),
            len(created),
            len(updated),
            unchanged,
        )
        return {
            "status": "SUCCESS" if created or updated else "IDLE",
            "apply": apply,
            "candidate_count": len(candidates),
            "created_count": len(created),
            "updated_count": len(updated),
            "unchanged_count": unchanged,
            "source_counts": source_counts,
            "items": [
                self._serialize_candidate(item, action="CREATE")
                for item in created[:50]
            ] + [
                self._serialize_candidate(item, action="UPDATE")
                for item in updated[:50]
            ],
        }

    async def _safe_fetch(self, broker: Any, method_name: str, *args: Any) -> list[Any]:
        method = getattr(broker, method_name, None)
        if method is None:
            return []
        try:
            result = await method(*args)
        except Exception as exc:
            logger.warning("stocks universe source {} failed: {}", method_name, str(exc))
            return []
        return list(result or [])

    async def _collect_objects(
        self,
        candidates_by_symbol: dict[str, StockUniverseCandidate],
        source_counts: dict[str, int],
        source: str,
        rows: list[Any],
    ) -> None:
        source_counts[source] = len(rows)
        for row in rows:
            self._add_candidate(candidates_by_symbol, source, row)

    async def _collect_rows(
        self,
        candidates_by_symbol: dict[str, StockUniverseCandidate],
        source_counts: dict[str, int],
        source: str,
        rows: list[Any],
        *,
        limit: int,
    ) -> None:
        limited = rows[:max(int(limit or 0), 0)]
        source_counts[source] = len(limited)
        for row in limited:
            self._add_candidate(candidates_by_symbol, source, row)

    def _add_candidate(
        self,
        candidates_by_symbol: dict[str, StockUniverseCandidate],
        source: str,
        row: Any,
    ) -> None:
        symbol = normalize_krx_symbol(self._read_value(row, "symbol", "code", "stock_code", "pdno"))
        name = str(self._read_value(row, "name", "stock_name", "prdt_name") or "").strip()
        if not symbol or not name:
            return
        category = self._read_optional(row, "category", "sector", "theme")
        market = self._read_optional(row, "market") or Market.KRX.value
        exchange_code = self._read_optional(row, "exchange_code")

        existing = candidates_by_symbol.get(symbol)
        if existing is None:
            existing = StockUniverseCandidate(
                symbol=symbol,
                name=name,
                market=str(market),
                category=category,
                exchange_code=exchange_code,
            )
            candidates_by_symbol[symbol] = existing
        else:
            if not existing.name or existing.name == existing.symbol:
                existing.name = name
            if not existing.category and category:
                existing.category = category
            if not existing.exchange_code and exchange_code:
                existing.exchange_code = exchange_code
        existing.sources.add(source)

    @staticmethod
    async def _load_existing(session: AsyncSession, symbols: list[str]) -> dict[str, Stock]:
        if not symbols:
            return {}
        result = await session.execute(select(Stock).where(Stock.symbol.in_(symbols)))
        return {stock.symbol: stock for stock in result.scalars().all()}

    @staticmethod
    def _stock_changes(stock: Stock, candidate: StockUniverseCandidate) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if stock.name != candidate.name:
            changes["name"] = candidate.name
        if stock.market != candidate.market:
            changes["market"] = candidate.market
        if candidate.category and stock.category != candidate.category:
            changes["category"] = candidate.category
        if candidate.exchange_code and stock.exchange_code != candidate.exchange_code:
            changes["exchange_code"] = candidate.exchange_code
        if not stock.is_active:
            changes["is_active"] = True
        return changes

    @staticmethod
    def _read_value(row: Any, *keys: str) -> Any:
        for key in keys:
            if isinstance(row, dict):
                value = row.get(key)
            else:
                value = getattr(row, key, None)
            if value not in (None, ""):
                return value
        return None

    def _read_optional(self, row: Any, *keys: str) -> str | None:
        value = self._read_value(row, *keys)
        if value in (None, ""):
            return None
        return str(value).strip()

    @staticmethod
    def _serialize_candidate(candidate: StockUniverseCandidate, *, action: str) -> dict[str, Any]:
        return {
            "action": action,
            "symbol": candidate.symbol,
            "name": candidate.name,
            "market": candidate.market,
            "category": candidate.category,
            "exchange_code": candidate.exchange_code,
            "sources": sorted(candidate.sources),
        }


stock_universe_bootstrap_service = StockUniverseBootstrapService()
