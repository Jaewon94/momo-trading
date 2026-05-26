# Brief

## Metadata

- Task ID: `2026-05-22-003-fix-transient-integrity`
- Created: `2026-05-22T13:25:54+09:00`
- Repo: `momo-trading`
- Title: Fix transient order integrity checks

## Goal

Prevent in-flight order confirmation windows from producing false broker/DB lifecycle integrity failures, verify with focused tests, and monitor runtime after the fix

## Scope

In scope:

- Adjust lifecycle integrity checks so fresh in-flight buy/sell confirmations are treated as transient `WARN` states, not broker/DB `FAIL` mismatches.
- Add regression tests for the exact false-fail pattern observed after today's live orders.
- Restart the local server in safe mode to load the fix and verify runtime integrity.
- Document any additional operational observations found during follow-up monitoring.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Re-enabling autonomous trading after the fix.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Existing runtime code and tests:
  - `services/trade_lifecycle_integrity_service.py`
  - `tests/services/test_trade_lifecycle_integrity_service.py`
  - `scripts/check_runtime_integrity.py`
- Previously consulted official guidance for the same supervised runtime work:
  - SEC Rule 15c3-5 market access risk controls.
  - FINRA algorithmic trading supervision/control guidance.
  - Kiwoom OpenAPI+ order documentation.

Plan implications:

- Adopt: pending confirmations inside the configured confirmation wait/timeout window remain warnings.
- Adopt: stale pending confirmations still fail when broker holdings and DB open positions disagree.
- Adopt: both buy and sell transient windows need coverage.
- Defer: separate UI wording change for `scheduler_running` when only news polling is enabled.
- Reject: hiding all pending confirmations; unresolved/stale pending rows must still surface.

## Completion Criteria

- Lifecycle integrity no longer reports `broker_untracked_holdings` for a fresh buy pending-confirm after broker pending disappears.
- Lifecycle integrity no longer reports `broker_missing_open_buys` for a fresh sell pending-confirm after broker holding drops.
- Stale pending-confirm rows still fail.
- Runtime is safe/read-only after verification.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python scripts/change_harness.py services/trade_lifecycle_integrity_service.py tests/services/test_trade_lifecycle_integrity_service.py`
- `python -m pytest tests/services/test_trade_lifecycle_integrity_service.py -q`
- `python -m pytest tests/scripts/test_check_runtime_integrity.py -q`
- `python scripts/check_runtime_integrity.py --base-url http://127.0.0.1:9000 --days 7 --timeout-sec 30 --allow-status OK --allow-status WARN --json`
- `GET /api/v1/admin/system/status`
- `GET /api/v1/admin/trades/lifecycle-integrity?days=7`
- `POST /api/v1/admin/account/snapshot/refresh`
