"""Local broker smoke test CLI."""
import argparse
import asyncio
import json

from services.broker_smoke_service import run_broker_smoke_test
from trading.broker_factory import get_broker_adapter
from trading.enums import Market


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only broker smoke checks")
    parser.add_argument("--symbol", default="005930", help="Symbol to quote during the smoke test")
    parser.add_argument("--market", default="KRX", help="Market code, e.g. KRX")
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    market = Market(args.market.upper())
    result = await run_broker_smoke_test(
        adapter=get_broker_adapter(),
        symbol=args.symbol,
        market=market,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
