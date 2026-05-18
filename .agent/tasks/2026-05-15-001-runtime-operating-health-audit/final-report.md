# Final Report

## Snapshot

- Checked at: `2026-05-15T10:20:52+09:00` through `2026-05-15T10:22:xx+09:00`.
- Server: running, PID `8040`.
- Health: OK.
- Broker/provider: `KIWOOM`.
- Runtime mode: `TRADING_ENABLED=true`, `AUTONOMOUS`, `ORDER_SUBMISSION_MODE=FULL`, scheduler/agent running.
- Admin dangerous action confirmation: enabled.

## Working As Intended

- Broker preflight is OK: balance, holdings, pending orders, and quote checks succeeded.
- News, Ollama, and observability maintenance are OK.
- LLM calls over the last 24h show 100% success in the observability overview.
- Recent activities show active Tier1 analysis, event detection, news polling, risk tuning, and holdings management.
- Today has real trading activity: confirmed buys/sells and partial exits are being recorded.

## Not Fully Healthy

- Runtime integrity gate is `FAIL`.
- Order reconciliation is `FAIL`:
  - broker pending count: `1`
  - DB pending count: `0`
  - broker-only pending order: `0067887`, `066430 아이로보틱스`, buy order qty `3250`, filled `25`, remaining `3225`.
- Lifecycle integrity is `FAIL`:
  - `confirm_failed=75`
  - `unpaired_sells=27`
  - `broker_missing_open_buys=18`
  - `broker_mismatched_open_buy_quantity=1465`
  - `repairable_sells=21`
- Today's risk-check logs show `일일거래: 0/30` even though AI risk tuning is recommending 6-8 daily trades and multiple buy attempts occurred. The effective risk counter/limit contract needs review.

## Account And Trading Notes

- Latest preflight balance: total asset about `481.1M`, cash about `441.8M`, stock value about `39.3M`.
- Today's baseline total asset: `482,898,833`.
- Latest snapshot total asset: `481,179,631`.
- Approx drawdown from baseline: about `-0.36%`, below the configured `0.5%` block-buy threshold but close enough to monitor.
- Current holdings: `005930`, `036540`, `066430`, `090710`, `215100`, `460940`.

## Recommendation

- Do not call this fully normal yet. It is running and trading, but not clean.
- Next safe step should be a separate approved operations task to handle:
  - broker-only pending order reconciliation for `0067887`;
  - lifecycle repair plan for unpaired sells/open buys;
  - review why risk checks show `0/30` and whether the dynamic AI daily trade limit is actually enforced.
