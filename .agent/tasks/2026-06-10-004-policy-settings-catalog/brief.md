# Brief

## Metadata

- Task ID: `2026-06-10-004-policy-settings-catalog`
- Created: `2026-06-10T12:20:48+09:00`
- Repo: `momo-trading`
- Title: Policy settings catalog

## Goal

Implement Phase 1 of the trading policy governance refactor by adding a centralized runtime policy settings catalog and sync tests without changing live trading behavior.

## Scope

In scope:

- Add a centralized catalog for mutable runtime settings that maps each setting
  to policy owner, scope, risk, mutability, and notes.
- Add tests that ensure all `core.runtime_settings.MUTABLE_SETTINGS` keys have
  catalog metadata.
- Update the refactor plan document with Phase 1 implementation status.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Changing setting values, validation ranges, admin API behavior, live runtime
  settings, trading thresholds, or order behavior.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `docs/architecture/trading-policy-engine-refactor-plan.md`
- `docs/workflows/trading-policy-change-checklist.md`

Plan implications:

- Adopt: catalog metadata and sync tests only.
- Defer: admin API response metadata and generated docs.
- Reject: live runtime setting mutation in this task.

## Completion Criteria

- Every mutable runtime setting has policy catalog metadata.
- Catalog tests pass.
- Existing admin settings validation tests remain compatible.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/strategy/policy tests/api/test_admin_settings_validation.py -q`
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-004-policy-settings-catalog`
