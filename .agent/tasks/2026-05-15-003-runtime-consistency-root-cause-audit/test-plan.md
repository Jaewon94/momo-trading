# Test Plan

Task: `2026-05-15-003-runtime-consistency-root-cause-audit`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/services/test_trade_close_reconciliation_service.py tests/services/test_trade_lifecycle_integrity_service.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_order_reconciliation_service.py tests/api/test_admin_trade_routes.py tests/scripts/test_check_runtime_integrity.py -q
.venv313/bin/python -m pytest tests/services/test_trade_lifecycle_integrity_service.py tests/scripts/test_check_runtime_integrity.py -q
python -m py_compile repositories/trade_result_repository.py services/order_reconciliation_service.py api/routes/admin.py scheduler/jobs/portfolio_sync_job.py scripts/check_runtime_integrity.py
python scripts/check_runtime_integrity.py --days 7
curl -s http://127.0.0.1:9000/api/v1/health
curl -s http://127.0.0.1:9000/api/v1/admin/system/status
curl -s http://127.0.0.1:9000/api/v1/admin/trades/reconciliation
curl -s http://127.0.0.1:9000/api/v1/admin/account/pending-orders
curl -s -X POST http://127.0.0.1:9000/api/v1/admin/trades/reconcile-holdings
.venv313/bin/python -m pytest tests/api/test_admin_mcp_routes.py tests/api/test_admin_trade_routes.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_order_reconciliation_service.py tests/services/test_trade_lifecycle_integrity_service.py tests/scripts/test_check_runtime_integrity.py -q
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm latest cycle completes after restart.
- Confirm remaining runtime FAIL gates map to explicit protected actions, not code-only false positives.

## Results

- `57 passed` for focused service/scheduler/API/runtime-gate suite.
- `58 passed` for the expanded focused suite after adding linked-non-pending order classification and holding-delta BUY recovery coverage.
- `py_compile` passed for modified repository/service/API/scheduler/runtime-gate modules.
- `40 passed` for incremental lifecycle/order-gate suite after partial-pending and neutral-close classification changes.
- `14 passed` for final lifecycle/runtime-gate focused rerun.
- `16 passed` for broker-untracked-holding lifecycle and runtime-gate focused rerun.
- Runtime restarted in tmux session `momo-trading-api`; health endpoint returned `healthy`.
- Latest observed cycle completed at `2026-05-15T13:06:06+09:00` with analysis `8`, recommendations `1`, trades `0`.
- Runtime integrity still fails because protected actions remain: broker-only pending order `0067887`, 20 broker-missing DB open BUY symbols, and 1 broker holding share not represented in DB for `066430`.
- `python scripts/task_harness.py verify 2026-05-15-003-runtime-consistency-root-cause-audit` reached the standard harness checks, but `harness_tests` was blocked because the tool invoked system Python 3.14 without pytest installed. This is recorded separately from the focused `.venv313` pytest results.
- Re-run confirmed `57 passed` for the focused suite and strict task harness passed after artifact status correction.
- Holdings reconciliation dry-run reports backfill candidate `0` and skipped `1` while broker pending order `0067887` remains; missing-close candidates remain `30` across `20` stale DB open BUY symbols.
- Runtime restarted in tmux session `momo-api-verify`; `health` returned `healthy` and `start.sh status` reports PID `48349`.
- Current order reconciliation reports `broker_pending_count=1`, `broker_linked_non_pending_count=1`, `broker_only_count=0`. The linked order is `0067887` for `066430`, broker filled `60`, remaining `3190`, DB linked row status `CONFIRMED` quantity `8`.
- Current holdings show only `066430` quantity `60`; lifecycle integrity fails on `broker_missing_open_buy_count=20`, `broker_missing_open_buy_quantity=33126`, `broker_untracked_holding_count=1`, `broker_untracked_holding_quantity=8`.
- 2026-05-18 runtime repair applied `MISSING_CLOSES`: 30 stale DB open BUY rows neutral-closed across 20 symbols.
- Post-repair `python scripts/check_runtime_integrity.py --days 7` passed with `system=OK`, `settings=OK`, `order_reconciliation=OK`, and lifecycle `status=OK`.
- Post-restart system status passed: PID `32549`, `health=healthy`, scheduler/agent running, `last_cycle_time=2026-05-18T09:18:52.058554+09:00`, operations broker/news/orders/account_snapshot all `OK`.
- Post-cycle holdings are `027360` 750 shares and `066430` 17 shares. Pending orders are `0`, DB pending confirms are `0`, broker missing/untracked holdings are `0`.
- Focused API/scheduler/service/runtime-gate suite passed `58 passed` after the stale order-error status recency fix.
- Latest cycle check confirmed cycle `2026-05-15T13:10:00+09:00` to `13:12:01+09:00`; system status `last_cycle_time` is `2026-05-15T13:12:01+09:00`.
- Latest cycle analyzed `8`, produced `1` BUY signal, and executed `0`; the order was blocked by the account equity drawdown guard at `-0.59% <= -0.50%`.
