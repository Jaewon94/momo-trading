# Brief

## Metadata

- Task ID: `2026-05-14-001-runtime-lifecycle-integrity-harness`
- Created: `2026-05-14T10:50:25+09:00`
- Repo: `momo-trading`
- Title: Runtime lifecycle integrity harness

## Goal

Add an explicit read-only runtime integrity gate so trading changes surface broker/DB/order lifecycle drift before they are treated as safe

## Scope

In scope:

- Add a read-only runtime integrity checker that calls existing local admin
  APIs and fails on lifecycle WARN/FAIL by default.
- Make `change_harness.py` surface that checker for trading, broker, DB,
  scheduler, service, and admin API changes.
- Update code-commit harness documentation and focused tests.
- Make scheduler sell paths consume the confirmation result so order receipt
  cannot be logged as sell completion when fill confirmation fails.
- Record the current live integrity failure as a verification finding, without
  applying DB repair or broker actions.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Automatic repair of current `trade_results`/broker position drift.
- Runtime setting changes such as disabling `AUTONOMOUS`/`FULL` without
  explicit approval.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `.agent/project-card.md`
- `.agent/current-task.json`
- `docs/workflows/code-commit-harness.md`
- `scripts/task_harness.py`
- `scripts/change_harness.py`
- `api/routes/admin.py` lifecycle integrity route
- Live read-only `/api/v1/admin/trades/lifecycle-integrity` result from
  2026-05-14 10:45 KST

Plan implications:

- Adopt: existing code/commit harness remains local and deterministic; runtime
  integrity becomes a separate explicit gate because it depends on a running
  server and live broker/DB state.
- Adopt: trading-sensitive change classification must mention runtime
  lifecycle integrity, not only focused unit tests.
- Defer: applying close reconciliation or neutral-closing stale open lots,
  because those mutate the runtime DB and need separate approval.
- Reject: treating activity-log "order complete" rows as sufficient proof of
  clean trade lifecycle completion.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.
- Runtime integrity checker fails against the current known bad live state and
  prints actionable counts.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py tests/scripts/test_check_runtime_integrity.py tests/scripts/test_change_harness.py -q`
- `python scripts/check_runtime_integrity.py --days 7` (expected to fail until
  live broker/DB drift is repaired)
- `python scripts/change_harness.py scheduler/scheduler.py`
- `.venv313/bin/python scripts/task_harness.py verify 2026-05-14-001-runtime-lifecycle-integrity-harness`
