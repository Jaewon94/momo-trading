# Brief

## Metadata

- Task ID: `2026-05-13-001-sell-pipeline-hardening`
- Created: `2026-05-13T12:21:46+09:00`
- Repo: `momo-trading`
- Title: Sell pipeline hardening

## Goal

Improve holdings sell monitoring with deterministic fast checks, strategy-aware exits, and tests while preserving broker/order guardrails

## Scope

In scope:

- Add deterministic holdings exit policy helpers for faster sell monitoring.
- Make scheduled holdings checks strategy-aware for short/mid/long horizons.
- Preserve existing broker/order placement path and duplicate sell guard.
- Add focused tests for partial profit, trailing/breakeven, soft-stop deferral,
  and strategy-aware sell behavior.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Live broker order submission, runtime setting flips, and data repair.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Existing plan: `docs/고도화/2026-05-08-buy-sell-ai-pipeline-redesign.md`.
- Investor.gov order type guidance: market orders do not guarantee execution
  price; stop orders become market orders; stop-limit controls price but may
  not execute.
- IBKR bracket/exit strategy guidance: combine profit taking and stop orders
  around a position to limit loss and protect profit.
- IBKR trailing stop limit guidance: trailing stops follow favorable price
  movement and hold fixed on adverse movement.
- Alpaca bracket/OCO guidance: take-profit and stop-loss legs should be managed
  as a group and remaining quantities adjusted after partial fills.

Plan implications:

- Adopt: hard risk rules remain deterministic and ahead of AI; profit protection
  uses partial take profit, breakeven stop, and trailing drawdown.
- Adopt: strategy horizon changes exit aggressiveness; short-term is more
  responsive than mid/long.
- Defer: broker-native OCO/bracket order submission because Kiwoom adapter
  capability and order replacement semantics need a separate broker-specific
  task.
- Defer: removing Tier1 buy LLM; this task focuses on sell/holdings behavior.
- Reject: letting AI override hard stop or broker reconciliation safeguards.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.
- No runtime DB reset, live sell order, migration, or broker credential change.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q`
- `python scripts/change_harness.py scheduler/scheduler.py tests/scheduler/test_scheduler_runtime_paths.py`
- `python scripts/task_harness.py verify 2026-05-13-001-sell-pipeline-hardening`
