"""Read-only broker smoke test helpers."""
import asyncio
from datetime import datetime

from trading.adapters.base import BrokerAdapter
from trading.enums import Market


async def run_broker_smoke_test(
    *,
    adapter: BrokerAdapter,
    symbol: str,
    market: Market = Market.KRX,
) -> dict:
    """Collect read-only broker checks for local smoke testing."""
    balance_result, holdings_result, pending_orders_result, quote_result = await asyncio.gather(
        adapter.get_balance(),
        adapter.get_holdings(),
        adapter.get_pending_orders(),
        adapter.get_current_price(symbol, market),
        return_exceptions=True,
    )

    checks = {
        "balance": _serialize_balance_check(balance_result),
        "holdings": _serialize_holdings_check(holdings_result),
        "pending_orders": _serialize_pending_orders_check(pending_orders_result),
        "quote": _serialize_quote_check(quote_result),
    }

    return {
        "ok": all(check["ok"] for check in checks.values()),
        "provider": adapter.provider.value,
        "symbol": symbol,
        "market": market.value,
        "capabilities": adapter.capabilities.model_dump(mode="json"),
        "checked_at": datetime.now().isoformat(),
        "checks": checks,
    }


def _serialize_balance_check(result: object) -> dict:
    if isinstance(result, Exception):
        return {"ok": False, "error": str(result)}
    return {
        "ok": bool(result.is_valid),
        "total_asset": result.total_asset,
        "cash": result.cash,
        "stock_value": result.stock_value,
        "total_pnl": result.total_pnl,
        "total_pnl_rate": result.total_pnl_rate,
    }


def _serialize_holdings_check(result: object) -> dict:
    if isinstance(result, Exception):
        return {"ok": False, "error": str(result)}
    return {
        "ok": True,
        "count": len(result),
        "symbols": [holding.symbol for holding in result],
    }


def _serialize_pending_orders_check(result: object) -> dict:
    if isinstance(result, Exception):
        return {"ok": False, "error": str(result)}
    return {
        "ok": True,
        "count": len(result),
        "order_ids": [order.order_id for order in result],
    }


def _serialize_quote_check(result: object) -> dict:
    if isinstance(result, Exception):
        return {"ok": False, "error": str(result)}
    return {
        "ok": True,
        "symbol": result.symbol,
        "market": result.market.value,
        "price": result.price,
        "change": result.change,
        "change_rate": result.change_rate,
        "volume": result.volume,
        "timestamp": result.timestamp.isoformat(),
    }
