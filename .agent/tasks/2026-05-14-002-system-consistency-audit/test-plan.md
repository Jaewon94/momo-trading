# Test Plan

Task: `2026-05-14-002-system-consistency-audit`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/api/test_admin_trade_routes.py tests/api/test_admin_account_routes.py tests/scripts/test_check_runtime_integrity.py -q
.venv313/bin/python -m pytest tests/scheduler/test_portfolio_sync_job.py tests/scheduler/test_scheduler_runtime_paths.py tests/agent/test_decision_maker.py -q
pnpm test:ui
python scripts/check_docs_consistency.py
python scripts/change_harness.py api/routes/admin.py scheduler/jobs/portfolio_sync_job.py scripts/check_runtime_integrity.py admin/static/js/app.js core/config.py
python scripts/check_runtime_integrity.py --days 7 --json
.venv313/bin/python scripts/task_harness.py verify 2026-05-14-002-system-consistency-audit
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.

## Results

- `.venv313/bin/python -m pytest tests/api/test_admin_trade_routes.py tests/api/test_admin_account_routes.py tests/scripts/test_check_runtime_integrity.py -q` → passed, 39 tests.
- `.venv313/bin/python -m pytest tests/scheduler/test_portfolio_sync_job.py tests/scheduler/test_scheduler_runtime_paths.py tests/agent/test_decision_maker.py -q` → passed, 145 tests.
- `pnpm test:ui` → passed, 33 files / 142 tests.
- `python scripts/check_docs_consistency.py` → passed.
- `python scripts/change_harness.py api/routes/admin.py scheduler/jobs/portfolio_sync_job.py scripts/check_runtime_integrity.py admin/static/js/app.js core/config.py` → high/protected; checks include runtime integrity, API, scheduler, scripts, frontend, config review.
- `python scripts/check_runtime_integrity.py --days 7 --json` → expected live fail: system OK, order reconciliation OK with broker_pending=0/db_pending=0 and no stale/mismatch counts, settings WARN because admin confirmation is disabled in the running server, lifecycle FAIL with pending=0, confirm_failed=54, unpaired_sells=14, broker_missing_open_buys=11, broker_mismatch_qty=8.
