# Test Plan

Task: `2026-05-22-001-read-only-runtime-check`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
bash start.sh backup-db
sqlite3 -readonly runtime/data/app.db "select key,value_json from runtime_settings where key in ('TRADING_ENABLED','ORDER_SUBMISSION_MODE','AUTONOMY_MODE','SCHEDULER_ENABLED','NEWS_POLL_ENABLED') order by key;"
bash start.sh status
curl -sS -m 5 http://127.0.0.1:9000/api/v1/health
curl -sS -m 5 -o /dev/null -w "%{http_code} %{content_type}\n" http://127.0.0.1:9000/admin
curl -sS -m 5 -o /dev/null -w "%{http_code} %{content_type}\n" http://127.0.0.1:9000/admin/static/js/app.js
.venv313/bin/python scripts/check_runtime_integrity.py --base-url http://127.0.0.1:9000 --days 7 --timeout-sec 30 --allow-status OK --allow-status WARN --json
```

## Results

- DB backup created: `runtime/backups/db/app-cli-20260522-103754.db`
- Runtime settings after update:
  - `TRADING_ENABLED=false`
  - `ORDER_SUBMISSION_MODE="READ_ONLY"`
  - `AUTONOMY_MODE="SEMI_AUTO"`
  - `SCHEDULER_ENABLED=false`
  - `NEWS_POLL_ENABLED=false`
- Normal runtime entrypoint started successfully in tmux session `momo-readonly-runtime`.
- `bash start.sh status`: running on `http://127.0.0.1:9000/admin` with PID `60008`.
- `/api/v1/health`: `SUCCESS`, `status=healthy`.
- `/admin`: `200 text/html`.
- `/admin/static/js/app.js`: `200 text/javascript`.
- `/api/v1/admin/settings`: read-only controls confirmed.
- `/api/v1/admin/system/status`: broker `KIWOOM`, effective order mode `DISABLED`,
  scheduler `false`, agent `true`, market session `KRX_NXT`.
- `/api/v1/admin/account/holdings`: `SUCCESS`, 3 holdings returned.
- Runtime integrity: `OK`; broker pending 0, DB pending 0, broker-only 0,
  quantity mismatch 0, lifecycle broker mismatch 0.

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
