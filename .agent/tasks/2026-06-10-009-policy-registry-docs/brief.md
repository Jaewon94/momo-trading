# Brief

## Metadata

- Task ID: `2026-06-10-009-policy-registry-docs`
- Created: `2026-06-10T12:50:38+09:00`
- Repo: `momo-trading`
- Title: Policy registry docs

## Goal

Implement Phase 4 of the trading policy governance refactor by adding a canonical policy registry and docs consistency tests without changing trading behavior.

## Scope

In scope:

- Add a canonical policy registry for owner, priority, scope, settings, and
  required tests.
- Add generated/verified governance documentation from the registry.
- Add tests that prevent registry/docs drift.
- Update the refactor plan with Phase 4 status.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Changing runtime settings, thresholds, policy behavior, broker/order path, or
  LLM prompt semantics.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `docs/architecture/trading-policy-engine-refactor-plan.md`
- `docs/architecture/trading-policy-governance.md`
- `docs/workflows/trading-policy-change-checklist.md`
- `strategy/policy/settings_catalog.py`

Plan implications:

- Adopt: registry metadata and consistency tests only.
- Defer: making registry drive runtime execution.
- Reject: behavior tuning in this task.

## Completion Criteria

- Registry covers known policy owners from the governance document and settings
  catalog.
- Governance document includes a registry-generated section.
- Tests fail if generated registry docs drift.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/strategy/policy tests/scripts/test_docs_harness_checks.py -q`
- `.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py tests/strategy/test_risk_manager_enhancements.py tests/agent/test_trading_agent_cycles.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-009-policy-registry-docs`
