# Brief

## Metadata

- Task ID: `2026-05-22-001-read-only-runtime-check`
- Created: `2026-05-22T10:37:32+09:00`
- Repo: `momo-trading`
- Title: Read-only runtime startup check

## Goal

Start momo-trading in read-only operational mode and verify health/admin/runtime status without enabling order submission

## Scope

In scope:

- Confirm whether the app is currently running on port 9000.
- Back up the runtime DB before changing persisted runtime settings.
- Set persisted runtime controls to read-only operation:
  `TRADING_ENABLED=false`, `ORDER_SUBMISSION_MODE=READ_ONLY`,
  `AUTONOMY_MODE=SEMI_AUTO`, `SCHEDULER_ENABLED=false`, `NEWS_POLL_ENABLED=false`.
- Start the app with the normal runtime entrypoint and verify health, Admin UI,
  broker read-only access, and runtime integrity.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, destructive migration, deploy, order placement, or automatic trading enablement.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `.agent/project-card.md`
- `.agent/current-task.json`
- `scripts/dev/start.sh`
- `main.py`
- `core/order_submission.py`
- `scheduler/scheduler.py`
- `runtime_settings` rows in `runtime/data/app.db`

Plan implications:

- Adopt: use read-only runtime settings before normal startup because the persisted
  DB settings overrode `.env` and had autonomous trading enabled.
- Defer: enabling autonomous/full order mode requires a separate explicit approval.
- Reject: plain `start.sh` before lowering persisted settings during live KRX session.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `bash start.sh backup-db`
- `sqlite3 -readonly runtime/data/app.db "select key,value_json ..."`
- `bash start.sh` in `tmux` read-only runtime session
- `curl -sS http://127.0.0.1:9000/api/v1/health`
- `curl -sS -o /dev/null -w "%{http_code} %{content_type}\n" http://127.0.0.1:9000/admin`
- `GET /api/v1/admin/settings`
- `GET /api/v1/admin/system/status`
- `GET /api/v1/admin/account/holdings`
- `.venv313/bin/python scripts/check_runtime_integrity.py --base-url http://127.0.0.1:9000 --days 7 --timeout-sec 30 --allow-status OK --allow-status WARN --json`
