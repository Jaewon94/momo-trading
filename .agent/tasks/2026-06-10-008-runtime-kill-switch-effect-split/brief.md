# Brief

## Metadata

- Task ID: `2026-06-10-008-runtime-kill-switch-effect-split`
- Created: `2026-06-10T12:47:37+09:00`
- Repo: `momo-trading`
- Title: Runtime kill switch effect split

## Goal

Implement the remaining Phase 3 runtime kill-switch split by separating runtime setting effects from enforcement while preserving existing kill-switch behavior.

## Scope

In scope:

- Separate TradingGuard runtime kill-switch effect construction from
  enforcement.
- Preserve existing `AUTO_RISK_KILL_SWITCH_ENABLED` behavior and trigger
  conditions.
- Add tests for generated runtime effects and enforcement calls.
- Update the refactor plan with Phase 3c status.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Changing kill-switch thresholds, defaults, trigger conditions, runtime setting
  keys, or broker/order behavior.
- Manually toggling live runtime settings.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `docs/architecture/trading-policy-engine-refactor-plan.md`
- `docs/workflows/trading-policy-change-checklist.md`
- `strategy/trading_guard.py`
- `tests/strategy/test_trading_guard.py`

Plan implications:

- Adopt: explicit runtime effect payload plus enforcement helper.
- Defer: broader runtime policy engine integration.
- Reject: kill-switch threshold/default tuning in this task.

## Completion Criteria

- Kill-switch results include runtime effect metadata when enabled.
- Runtime settings update still occurs when kill switch is enabled.
- No runtime settings update occurs when kill switch is disabled.
- Focused tests and runtime integrity pass.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py tests/strategy/test_risk_manager_enhancements.py -q`
- `.venv313/bin/python -m pytest tests/strategy/policy tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-008-runtime-kill-switch-effect-split`
