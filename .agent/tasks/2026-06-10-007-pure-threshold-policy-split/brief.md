# Brief

## Metadata

- Task ID: `2026-06-10-007-pure-threshold-policy-split`
- Created: `2026-06-10T12:42:56+09:00`
- Repo: `momo-trading`
- Title: Pure threshold policy split

## Goal

Implement the remaining Phase 3 threshold split by separating trade threshold calculation from event detector enforcement while preserving existing _apply_trade_thresholds behavior.

## Scope

In scope:

- Split trade threshold calculation from event-detector enforcement.
- Preserve the existing `_apply_trade_thresholds` method as a compatibility
  wrapper.
- Add tests that verify pure threshold calculation does not call
  `event_detector.set_thresholds`.
- Update the refactor plan with Phase 3b status.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Changing stop-loss, take-profit, trailing-stop, horizon, or risk-appetite
  values.
- Changing event sell execution behavior.
- Runtime kill-switch side-effect extraction.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `docs/architecture/trading-policy-engine-refactor-plan.md`
- `docs/workflows/trading-policy-change-checklist.md`
- `agent/trading_agent.py`
- `tests/agent/test_trading_agent_cycles.py`

Plan implications:

- Adopt: pure calculation helper plus explicit enforcement helper.
- Defer: runtime kill-switch side-effect extraction.
- Reject: threshold tuning in this task.

## Completion Criteria

- `_resolve_trade_thresholds` computes the same threshold payload without
  event-detector side effects.
- `_enforce_trade_thresholds` is the only helper that writes to event detector
  for trade thresholds.
- Existing `_apply_trade_thresholds` tests continue to pass.
- New pure-helper test prevents accidental side effects.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py -q`
- `.venv313/bin/python -m pytest tests/strategy/policy tests/strategy/test_risk_manager_enhancements.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-007-pure-threshold-policy-split`
