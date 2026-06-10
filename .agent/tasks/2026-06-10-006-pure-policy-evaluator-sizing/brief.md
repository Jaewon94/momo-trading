# Brief

## Metadata

- Task ID: `2026-06-10-006-pure-policy-evaluator-sizing`
- Created: `2026-06-10T12:37:35+09:00`
- Repo: `momo-trading`
- Title: Pure policy evaluator sizing

## Goal

Implement Phase 3a of the trading policy governance refactor by removing direct quantity mutation from policy evaluators where feasible while preserving final order parameters through caller enforcement and parity tests.

## Scope

In scope:

- Remove direct `TradeSignal.suggested_quantity` mutation from `RiskManager.check`.
- Make aggressive exposure alignment return decision/effect metadata while the
  caller enforces final quantity.
- Preserve final order quantity behavior through caller enforcement.
- Add/update parity tests for adjusted quantity and mutation boundaries.
- Update the refactor plan with Phase 3a status.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Changing thresholds, risk limits, default runtime settings, broker buying
  power caps, order request construction, liquidation behavior, or LLM prompts.
- Refactoring kill switch runtime setting updates.
- Splitting trade threshold event-detector enforcement.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `docs/architecture/trading-policy-engine-refactor-plan.md`
- `docs/workflows/trading-policy-change-checklist.md`
- `strategy/risk_manager.py`
- `agent/trading_agent.py`

Plan implications:

- Adopt: quantity mutation removal where caller already has enforcement point.
- Defer: kill switch side-effect extraction and threshold/event-detector split.
- Reject: any tuning of risk/exposure values in this task.

## Completion Criteria

- Risk manager returns the same adjusted quantity without mutating the signal.
- Trading agent still applies the same final risk/exposure quantity before order
  submission.
- Focused tests cover mutation boundary and final quantity parity.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/strategy/test_risk_manager_enhancements.py tests/agent/test_trading_agent_cycles.py tests/strategy/policy -q`
- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cost_gate.py tests/agent/test_trading_agent_news_gate.py tests/agent/test_order_reservation.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-006-pure-policy-evaluator-sizing`
