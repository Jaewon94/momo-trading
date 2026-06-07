# Test Plan

Task: `2026-06-03-001-weekly-trading-review`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python scripts/task_harness.py status
sqlite3 runtime/data/app.db "<read-only weekly trade/report/settings/activity queries>"
curl -s http://127.0.0.1:9000/api/v1/health
curl -s http://127.0.0.1:9000/api/v1/admin/system/status
curl -s http://127.0.0.1:9000/api/v1/admin/account/balance
curl -s http://127.0.0.1:9000/api/v1/admin/account/holdings
curl -s http://127.0.0.1:9000/api/v1/admin/trades/reconciliation
curl -s "http://127.0.0.1:9000/api/v1/admin/trades/lifecycle-integrity?days=7"
curl -s "http://127.0.0.1:9000/api/v1/admin/performance/summary?days=7"
python scripts/check_runtime_integrity.py --days 7 --allow-status OK --allow-status WARN
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm runtime DB was only read, not mutated.
- Confirm 2026-06-03 fixture-like decision events are treated as contamination until user approves cleanup.
- Confirm 2026-06-04 fixture-like `005930` decision events are treated as benchmark contamination until user approves cleanup or code excludes them.
- Confirm no pending broker/DB reconciliation mismatch remains after the 2026-06-04 ledger repair.
