# Test Plan

Task: `2026-05-15-001-runtime-operating-health-audit`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
bash start.sh status
curl -s http://127.0.0.1:9000/api/v1/health
.venv313/bin/python scripts/check_runtime_integrity.py --days 7 --json
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Check system/status, settings, preflight, order reconciliation, lifecycle integrity, pending orders, holdings, today's trades, recent activities, and observability overview through read-only GETs.
- Read-only SQLite queries were used to separate real buy/sell rows from holding-sync backfill rows.
