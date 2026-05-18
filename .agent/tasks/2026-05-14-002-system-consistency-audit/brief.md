# Brief

## Metadata

- Task ID: `2026-05-14-002-system-consistency-audit`
- Created: `2026-05-14T11:33:03+09:00`
- Repo: `momo-trading`
- Title: System consistency audit and fixes

## Goal

Find other repo/runtime mismatch surfaces beyond trade lifecycle integrity, fix code-level inconsistencies, and document remaining protected operational repairs

## Scope

In scope:

- Inventory existing consistency checks for broker pending orders, trade
  lifecycle, runtime settings, and admin repair actions.
- Extend the read-only runtime gate so it checks system status, runtime
  settings, broker/DB pending reconciliation, and lifecycle integrity together.
- Make protected admin repair/order endpoints require server-side confirmation
  tokens and make holdings reconciliation default to dry-run.
- Update documentation and tests for the new consistency contract.
- Record live read-only findings without applying DB repair, broker cancel,
  baseline reset, runtime mode changes, or restart.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Applying close reconciliation, stale pending cleanup, holdings repair, or
  runtime setting changes against the live database.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `.agent/project-card.md`
- `.agent/current-task.json`
- `services/order_reconciliation_service.py`
- `services/trade_lifecycle_integrity_service.py`
- `services/stale_pending_cleanup_service.py`
- `services/trade_close_reconciliation_service.py`
- `scheduler/jobs/portfolio_sync_job.py`
- `api/routes/admin.py`
- `admin/static/js/app.js`
- Live read-only health, system status, settings, pending order reconciliation,
  close reconciliation, lifecycle integrity, and holdings endpoints

Plan implications:

- Adopt: runtime integrity should be a multi-section gate, not only a lifecycle
  endpoint wrapper.
- Adopt: endpoints that mutate broker/DB state need server-side confirmation
  regardless of the local UI setting.
- Adopt: holdings reconciliation should be dry-run by default; applying
  backfill, zero-price repair, or neutral closes must be explicit.
- Defer: live DB repair and restart because they are protected operational
  actions.
- Reject: relying on UI `window.confirm` or a false runtime setting as the only
  protection for reset/order/cancel/repair actions.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/api/test_admin_trade_routes.py tests/api/test_admin_account_routes.py tests/scripts/test_check_runtime_integrity.py -q`
- `.venv313/bin/python -m pytest tests/scheduler/test_portfolio_sync_job.py tests/scheduler/test_scheduler_runtime_paths.py tests/agent/test_decision_maker.py -q`
- `pnpm test:ui`
- `python scripts/check_docs_consistency.py`
- `python scripts/change_harness.py api/routes/admin.py scheduler/jobs/portfolio_sync_job.py scripts/check_runtime_integrity.py admin/static/js/app.js core/config.py`
- `python scripts/check_runtime_integrity.py --days 7 --json`
- `.venv313/bin/python scripts/task_harness.py verify 2026-05-14-002-system-consistency-audit`
