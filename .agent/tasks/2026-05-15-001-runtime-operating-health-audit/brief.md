# Brief

## Metadata

- Task ID: `2026-05-15-001-runtime-operating-health-audit`
- Created: `2026-05-15T10:21:05+09:00`
- Repo: `momo-trading`
- Title: Runtime operating health audit

## Goal

Read-only audit of live runtime health, trading behavior alignment, consistency drift, and remaining operational gaps

## Scope

In scope:

- Read-only live runtime health check.
- Verify server/process, trading mode, scheduler/agent, broker preflight, pending orders, holdings, today trades, recent activities, observability, and runtime integrity gate.
- Identify whether the system is operating as intended and list remaining operational gaps.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Local runtime API endpoints on `http://127.0.0.1:9000`.
- Read-only SQLite queries against `runtime/data/app.db`.
- `scripts/check_runtime_integrity.py --days 7 --json`.

Plan implications:

- Adopt: treat process/system/preflight OK separately from trade lifecycle integrity.
- Defer: DB repair, broker pending order cancellation, runtime mode changes, or any broker-affecting operation require separate approval.
- Reject: do not call protected POST repair/cancel/sell endpoints during this audit.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `bash start.sh status`
- `curl -s http://127.0.0.1:9000/api/v1/health`
- `GET /api/v1/admin/system/status`
- `GET /api/v1/admin/settings`
- `GET /api/v1/admin/system/preflight`
- `GET /api/v1/admin/trades/reconciliation`
- `GET /api/v1/admin/trades/lifecycle-integrity?days=7`
- `GET /api/v1/admin/account/holdings`
- `GET /api/v1/admin/account/pending-orders`
- `GET /api/v1/admin/trades?target_date=2026-05-15`
- `GET /api/v1/admin/activities?limit=20`
- `GET /api/v1/admin/observability/overview?hours=24&points=24`
