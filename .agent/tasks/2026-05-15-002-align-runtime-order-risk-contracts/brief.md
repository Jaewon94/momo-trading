# Brief

## Metadata

- Task ID: `2026-05-15-002-align-runtime-order-risk-contracts`
- Created: `2026-05-15T10:29:15+09:00`
- Repo: `momo-trading`
- Title: Align runtime order and risk contracts

## Goal

Fix code-level gaps causing broker-only partial pending orders, lifecycle drift growth, and risk daily counter mismatch without mutating live broker or DB state

## Scope

In scope:

- Keep broker orders with remaining quantity in `PENDING_CONFIRM` instead of marking them `CONFIRMED`.
- Align portfolio-sync pending recovery with the same partial-fill contract.
- Count today's BUY order attempts from `trade_results` lifecycle rows instead of the legacy `orders` table.
- Surface effective dynamic risk limits in risk-check results/log detail.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Manual repair of the currently live broker-only pending order without explicit approval.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Runtime health/report/admin endpoints from the active local API.
- `agent/decision_maker.py`, `scheduler/jobs/portfolio_sync_job.py`, `agent/trading_agent.py`, `strategy/risk_manager.py`.
- Existing tests for decision maker, portfolio sync, trading agent market data, and risk cash-ratio behavior.

Plan implications:

- Adopt: partial fills with broker remaining quantity are not settled and keep their DB pending row.
- Adopt: daily risk count means actual BUY order attempts: `PENDING_CONFIRM`, `CONFIRMED`, and `CONFIRM_FAILED`, excluding `HOLDING_SYNC` backfills.
- Defer: current live order `0067887` DB repair or broker cancellation requires explicit protected-operation approval.
- Reject: treating a partial fill as a fully confirmed TradeResult while broker 잔량 remains open.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_portfolio_sync_job.py tests/agent/test_trading_agent_market_data.py tests/strategy/test_cash_ratio_units.py`
- `python scripts/task_harness.py verify 2026-05-15-002-align-runtime-order-risk-contracts`
- Read-only runtime integrity check after restart.
