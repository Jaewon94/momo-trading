# Decision Record

## Decision

- Do not mark the system as fully healthy while runtime integrity is `FAIL`.
- Process/system/preflight are healthy: server PID 8040 is alive, health OK, KIWOOM preflight OK, scheduler/agent running, `TRADING_ENABLED=true`, `AUTONOMOUS`, `ORDER_SUBMISSION_MODE=FULL`.
- Trading behavior is active and broadly aligned with the desired automated mode, but operational trust is reduced by order reconciliation and lifecycle drift.

## Rationale

- Broker shows one pending buy order `0067887` for `066430` that is broker-only from the reconciliation perspective: order quantity 3250, filled 25, remaining 3225. DB has confirmed/backfilled only the filled holding quantity and no matching pending-confirm row.
- Lifecycle integrity reports accumulated drift: `confirm_failed=75`, `unpaired_sells=27`, `broker_missing_open_buys=18`, `broker_mismatched_open_buy_quantity=1465`.
- Today's risk-check logs repeatedly show `일일거래: 0/30` while AI risk tuning recommends 6-8 daily trades and there are multiple buy attempts. This suggests the effective risk counter/limit contract is not aligned with the AI tuning output.

## Deferred

- No broker order cancellation, DB repair/apply, mode change, or reset was performed.
- Repairing lifecycle records and reconciling broker-only pending order state require a separate approved operations task.

## Risks

- Live trading remains enabled in FULL/AUTONOMOUS while integrity is failing.
- Current account drawdown from today's baseline is roughly -0.36%, below the 0.5% block-buy threshold but close enough to keep monitoring.
- Several stale observability incidents remain open, mostly news/admin API errors from prior days.
