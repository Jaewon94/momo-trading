# Final Report

## Status

Blocked on protected live-state remediation.

## What Changed

- Kept broker partial fills with remaining quantity in `PENDING_CONFIRM` instead of settling them as fully confirmed.
- Aligned the portfolio sync recovery path with the same partial-fill contract.
- Counted today's risk-limit usage from `trade_results` instead of the legacy order table.
- Propagated effective dynamic risk limits through the risk manager result so logs and guards use the AI-tuned values.

## Verification

- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_portfolio_sync_job.py tests/agent/test_trading_agent_market_data.py tests/strategy/test_cash_ratio_units.py` -> 83 passed.
- `.venv313/bin/python scripts/task_harness.py verify 2026-05-15-002-align-runtime-order-risk-contracts` -> passed.
- `.venv313/bin/python scripts/change_harness.py ...` -> high/protected risk classification, expected for decision/risk/order lifecycle logic.
- Restarted in background with tmux session `momo-trading-api`.
- Health check after restart: healthy.
- System status after restart: KIWOOM, trading enabled, AUTONOMOUS, effective order mode FULL, scheduler running, agent running, market session regular.
- First post-restart cycle completed at `2026-05-15T10:48:01+09:00`: analysis 8, recommendations/orders 0.

## Runtime Findings

- Read-only integrity remains `FAIL` because existing live state still has protected operational drift:
  - Broker-only pending buy order `0067887` for `066430 아이로보틱스`: order quantity 3,250, filled 28, remaining 3,222 at 3,080.
  - Lifecycle drift in the last 7 days: `confirm_failed=75`, `unpaired_sells=27`, `broker_missing_open_buys=18`, `broker_mismatched_open_buy_quantity=1465`, `repairable_sells=21`, `neutral_closes=14`.
  - Recent order warning remains from `083640 인콘`: simulated broker sellable quantity shortage at `2026-05-15T09:05:02`.
- These were not repaired because broker actions and runtime DB mutations are protected operations.

## Remaining Approval Boundary

To make runtime integrity fully green, an operator-approved repair is needed:

- Either restore/create a DB pending record for broker order `0067887`, or cancel/otherwise reconcile the broker-side remaining order.
- Reconcile historical lifecycle rows by pairing repairable sells and closing DB-only open buys that the broker no longer holds.
- Re-run `python scripts/check_runtime_integrity.py --days 7` after the approved repair.
