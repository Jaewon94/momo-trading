# Test Plan

Task: `2026-05-22-002-enable-supervised-runtime`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
bash start.sh status
python scripts/check_runtime_integrity.py --base-url http://127.0.0.1:9000 --days 7 --timeout-sec 30 --allow-status OK --allow-status WARN --json
```

## Manual Checks

- Confirm protected runtime setting changes used admin confirmation tokens.
- Confirm preflight broker/news/observability checks pass before enabling.
- Confirm account snapshot freshness before and after live activity.
- Confirm live orders are visible in activities/trades and pending orders reconcile.
- Confirm any runtime integrity `FAIL` results in safe fallback before more autonomous orders.
- Confirm final state has no broker-only, DB-only, stale, quantity mismatch, or untracked holding issues.
