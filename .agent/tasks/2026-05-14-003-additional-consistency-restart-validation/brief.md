# Brief

## Metadata

- Task ID: `2026-05-14-003-additional-consistency-restart-validation`
- Created: `2026-05-14T11:56:45+09:00`
- Repo: `momo-trading`
- Title: Additional consistency sweep and restart validation

## Goal

Check for remaining protected-action and consistency drift surfaces, patch any code-level gaps, then restart the local server and verify the new behavior is active

## Scope

In scope:

- Inventory remaining admin/API write surfaces after the lifecycle-integrity fix.
- Align high-risk runtime setting writes, credential writes, scheduler controls, and manual agent trigger with server-side confirmation tokens.
- Restore any discovered UI/test contract drift that blocks verification.
- Restart the local server after code verification and run safe post-restart checks.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `api/routes/admin.py`
- `api/routes/orders.py`
- `api/routes/recommendations.py`
- `admin/static/js/app.js`
- `admin/static/index.html`
- `docs/workflows/code-commit-harness.md`
- `tests/api/*`

Plan implications:

- Adopt: require server-side confirmation tokens for risky admin write endpoints even when the runtime confirmation setting is disabled.
- Adopt: keep generic `/orders` create/cancel classified as DB-only CRUD because it does not submit broker orders through `OrderService`.
- Defer: no live DB repair or broker reconciliation is performed in this task.
- Reject: do not validate protections by sending live order/sell/cancel requests to the running broker-backed server.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python scripts/change_harness.py api/routes/admin.py admin/static/js/app.js admin/static/index.html docs/workflows/code-commit-harness.md tests/api/test_admin_settings_routes.py tests/api/test_admin_settings_validation.py tests/api/test_admin_scheduler_routes.py tests/api/test_admin_manual_actions.py`
- `.venv313/bin/python -m pytest tests/api -q`
- `.venv313/bin/python -m pytest tests/scripts/test_check_runtime_integrity.py tests/scripts/test_change_harness.py -q`
- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py tests/scheduler/test_portfolio_sync_job.py -q`
- `pnpm test:ui`
- `python scripts/check_docs_consistency.py`
- `python scripts/task_harness.py verify 2026-05-14-003-additional-consistency-restart-validation`
- Post-restart safe checks: health/status/settings/openapi/static JS/runtime integrity gate.
