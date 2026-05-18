# Final Report

## Summary

- Expanded `scripts/check_runtime_integrity.py` from a lifecycle-only check into
  a read-only runtime consistency gate covering health, system status, runtime
  settings, broker/DB pending order reconciliation, and lifecycle integrity.
- Fixed admin repair/action contracts:
  - `POST /trades/reconcile-holdings` is dry-run by default.
  - Applying holdings backfill, zero-price repair, missing closes, or quantity
    closes now requires explicit apply flags plus a server-side confirmation
    token.
  - Manual sell, pending cancel, cancel-and-sell, pending confirm recovery,
    stale pending cleanup apply, and operational baseline reset require
    server-side confirmation tokens.
- Updated admin UI dangerous-action calls to request confirmation tokens for
  protected POSTs instead of depending on a mutable runtime setting.
- Updated the code commit harness docs to state the broader runtime consistency
  gate and protected admin POST contract.

## Verification

- `.venv313/bin/python -m pytest tests/api/test_admin_trade_routes.py tests/api/test_admin_account_routes.py tests/scripts/test_check_runtime_integrity.py -q` → passed, 39 tests.
- `.venv313/bin/python -m pytest tests/scheduler/test_portfolio_sync_job.py tests/scheduler/test_scheduler_runtime_paths.py tests/agent/test_decision_maker.py -q` → passed, 145 tests.
- `pnpm test:ui` → passed, 33 files / 142 tests.
- `python scripts/check_docs_consistency.py` → passed.
- `python scripts/check_task_harness.py --strict-current` → passed.
- `.venv313/bin/python scripts/task_harness.py verify 2026-05-14-002-system-consistency-audit` → passed.

## Live Findings

- Running server: system OK, scheduler/agent running, `AUTONOMOUS`, effective
  order mode `FULL`.
- Order reconciliation: OK at read time, broker pending 0 and DB pending 0,
  with no broker-only, stale, quantity-mismatch, or partial-fill pending drift.
- Runtime settings: WARN because the running server still has
  `ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED=false`.
- Lifecycle integrity: FAIL with pending=0, confirm_failed=54,
  unpaired_sells=14, broker_missing_open_buys=11, broker_mismatch_qty=8.

## Deferred

- No live DB repair, broker cancel/order, baseline reset, runtime setting change,
  server restart, commit, or push was performed.
- The running process predates these code changes, so live behavior will not
  reflect the stricter route contracts until an approved restart.
