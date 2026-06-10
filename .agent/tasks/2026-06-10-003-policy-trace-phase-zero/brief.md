# Brief

## Metadata

- Task ID: `2026-06-10-003-policy-trace-phase-zero`
- Created: `2026-06-10T12:10:10+09:00`
- Repo: `momo-trading`
- Title: Policy trace phase zero

## Goal

Implement Phase 0 of the trading policy governance refactor by adding shared policy decision/trace types and behavior-preserving adapters for existing trading gates.

## Scope

In scope:

- Add shared policy decision/effect/trace types for trading policies.
- Add behavior-preserving adapters that translate existing gate outputs into
  the shared trace schema.
- Attach policy trace metadata to existing activity-log/detail paths for buy
  gates, risk sizing, exposure alignment, order submission, and exit events
  where practical without changing execution behavior.
- Add focused tests for trace adapters and representative call sites.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Changing buy/sell thresholds, order quantities, broker calls, runtime settings,
  DB schema, liquidation behavior, or LLM prompt semantics.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `docs/architecture/trading-policy-engine-refactor-plan.md`
- `docs/workflows/trading-policy-change-checklist.md`
- `docs/architecture/trading-policy-governance.md`

Plan implications:

- Adopt: Phase 0 only. Trace existing decisions without changing behavior.
- Defer: Settings catalog, engine wrapper, pure evaluators, admin UI metadata.
- Reject: Threshold tuning or runtime policy changes in this task.

## Completion Criteria

- Shared trace types and adapters exist under `strategy/policy/`.
- Existing gate outputs can be serialized into a common `policy_trace` object.
- Representative code paths attach trace metadata without changing branch logic.
- Focused tests pass.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/strategy/policy -q`
- `.venv313/bin/python -m pytest tests/strategy/test_risk_manager.py tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py -q`
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-003-policy-trace-phase-zero`
