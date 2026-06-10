# Brief

## Metadata

- Task ID: `2026-06-10-005-policy-engine-wrapper`
- Created: `2026-06-10T12:28:19+09:00`
- Repo: `momo-trading`
- Title: Policy engine wrapper

## Goal

Implement Phase 2 of the trading policy governance refactor by adding a behavior-preserving TradingPolicyEngine facade for buy, order submission, and exit policy trace paths.

## Scope

In scope:

- Add a behavior-preserving `TradingPolicyEngine` facade for existing policy
  gates and trace adapters.
- Route representative buy-path, order-submission, and exit-event policy trace
  calls through the facade without changing gate order or thresholds.
- Add focused tests for facade parity and trace preservation.
- Update the refactor plan document with Phase 2 implementation status.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Changing buy/sell thresholds, runtime settings, LLM prompt semantics, order
  request construction, liquidation behavior, or broker reconciliation.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `docs/architecture/trading-policy-engine-refactor-plan.md`
- `docs/workflows/trading-policy-change-checklist.md`

Plan implications:

- Adopt: facade routing and trace parity only.
- Defer: pure evaluator mutation removal and generated registry docs.
- Reject: any strategy tuning or live runtime setting mutation in this task.

## Completion Criteria

- Existing policy gate behavior and return payloads remain compatible.
- `TradingAgent`, `DecisionMaker`, and exit-event trace paths can use the
  engine facade for policy decisions.
- Focused policy/agent tests pass.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/strategy/policy tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_news_gate.py tests/agent/test_trading_agent_cost_gate.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-005-policy-engine-wrapper`
