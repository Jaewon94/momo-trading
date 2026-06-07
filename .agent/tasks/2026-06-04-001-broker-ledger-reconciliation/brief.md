# Brief

## Metadata

- Task ID: `2026-06-04-001-broker-ledger-reconciliation`
- Created: `2026-06-04T10:12:56+09:00`
- Repo: `momo-trading`
- Title: Fix broker ledger reconciliation

## Goal

Identify and fix the mismatch where broker holdings can no longer include a sold position while admin trade_results still reports it as open, without placing orders or mutating runtime broker state during verification.

## Scope

In scope:

- Fix SELL confirmation bookkeeping for intraday holdings-review sells.
- Keep broker holdings as the source of truth for detecting stale DB-open BUY lots.
- Add regression coverage for ambiguous Kiwoom SELL confirmation where broker holdings already shrank.
- Update task artifacts with protected-area risk and verification results.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `.agent/project-card.md`
- `.agent/security-policy.md`
- `.agent/current-task.json`
- `docs/workflows/code-commit-harness.md`
- `api/routes/admin.py`
- `agent/decision_maker.py`
- `scheduler/scheduler.py`
- `scheduler/jobs/portfolio_sync_job.py`
- `services/trade_lifecycle_integrity_service.py`
- `tests/agent/test_decision_maker.py`
- `tests/scheduler/test_scheduler_runtime_paths.py`

Plan implications:

- Adopt: route intraday holdings-review SELL confirmation through the existing scheduler helper that creates a `PENDING_CONFIRM` SELL audit row.
- Adopt: invalidate broker cache before SELL holding-delta inference so a stale cached holding cannot leave a real sell unrecorded.
- Adopt: on SELL status timeout, attempt holding-delta inference before marking the pending row failed.
- Defer: applying `/admin/trades/reconcile-holdings?apply_missing_closes=true` to the live DB; this mutates runtime DB and needs explicit approval.
- Reject: changing buy/sell thresholds, risk appetite, liquidation policy, or order quantity rules for this task.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- Add task-specific commands here.
