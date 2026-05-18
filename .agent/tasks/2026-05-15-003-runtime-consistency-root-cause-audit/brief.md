# Brief

## Metadata

- Task ID: `2026-05-15-003-runtime-consistency-root-cause-audit`
- Created: `2026-05-15T12:40:02+09:00`
- Repo: `momo-trading`
- Title: Runtime consistency root cause audit

## Goal

Classify all live order, trade lifecycle, and holding consistency mismatches before any protected repair action.

## Scope

In scope:

- Runtime order reconciliation, trade lifecycle integrity, holding reconciliation, and status gate mismatches.
- Code/reporting fixes that do not place broker orders or mutate production trade state.
- Classification of protected follow-up actions needed to fully clear runtime FAIL gates.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Broker order cancellation and runtime DB neutral-close application without explicit approval.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `.agent/project-card.md`
- `.agent/current-task.json`
- `/api/v1/admin/system/status`
- `/api/v1/admin/trades/reconciliation`
- `/api/v1/admin/trades/lifecycle-integrity?days=7`
- `/api/v1/admin/trades/close-reconciliation?days=7`
- `/api/v1/admin/trades/reconcile-holdings` dry-run
- `scripts/check_runtime_integrity.py --days 7`

Plan implications:

- Adopt: Treat already-reflected SELL executions, terminal `CONFIRM_FAILED`, and neutral reconciliation closes as history/informational rather than active drift.
- Adopt: Block future holdings backfill when a broker pending order exists, preventing synthetic rows while an order is still live.
- Adopt: For Kiwoom SELL orders with `filled_qty=0` but broker-reported remaining quantity, recheck status before cancellation; the previous 3-second path could cancel protective sells before the broker status/feed caught up.
- Adopt: Treat the 2026-05-18 `011000` stale SELL `PENDING_CONFIRM` as terminal failed when broker holdings and DB open quantity already match, without issuing another broker cancel.
- Defer: Apply DB neutral-close for 30 stale open BUY lots until explicit approval.
- Defer: Cancel broker pending buy order `0067887` or otherwise perform protected broker/order repair until explicit approval.
- Reject: Hiding real broker/DB drift by downgrading `broker_only` or `broker_missing_open_buys` to OK.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.
- Runtime is restarted and health/cycle checks are repeated.
- Protected remaining actions are clearly separated from code-only fixes.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/services/test_trade_close_reconciliation_service.py tests/services/test_trade_lifecycle_integrity_service.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_order_reconciliation_service.py tests/api/test_admin_trade_routes.py tests/scripts/test_check_runtime_integrity.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
- `curl -s http://127.0.0.1:9000/api/v1/health`
- `curl -s http://127.0.0.1:9000/api/v1/admin/system/status`
