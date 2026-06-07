# Final Report

## Summary

Implemented a bounded fix for intraday holdings-review SELL bookkeeping.

- `scheduler/scheduler.py`: intraday holdings-review SELL and PARTIAL_SELL now route through `_track_scheduler_sell_confirmation`, so a SELL `PENDING_CONFIRM` audit row is created before confirmation.
- `agent/decision_maker.py`: SELL confirmation now invalidates broker cache before holding-delta inference. SELL timeout now attempts holding-delta inference before marking the pending row failed.
- Regression tests cover the intraday pending-record path and SELL timeout recovery when broker holdings already shrank.

## Verification

- Passed: `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py -q`
  - `136 passed, 3 warnings`
- Passed: `.venv313/bin/python scripts/task_harness.py verify 2026-06-04-001-broker-ledger-reconciliation`
- Failed as expected on live data: `python scripts/check_runtime_integrity.py --days 7`
  - Runtime status/settings/order reconciliation were OK.
  - Lifecycle failed with `broker_missing_open_buys=1`, matching the pre-existing `004060` DB-open/broker-missing position.

## Safety

No broker order, runtime DB repair, reset, migration, liquidation, service restart, commit, or push was performed.

## Remaining Risk

The current live `004060` mismatch is not automatically repaired by this code change. Applying `/api/v1/admin/trades/reconcile-holdings?apply_missing_closes=true` or equivalent DB repair would mutate runtime DB and requires explicit approval.
