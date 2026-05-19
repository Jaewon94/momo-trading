# Brief

## Metadata

- Task ID: `2026-05-20-001-mid-long-bias`
- Created: `2026-05-20T08:41:14+09:00`
- Repo: `momo-trading`
- Title: Harden mid long horizon bias

## Goal

Make mid and long horizons the primary trading behavior and demote short-term execution to rare bounded exceptions

## Scope

In scope:

- Make `MID` the default entry horizon and `LONG` the preferred horizon for high-confidence bull/theme setups.
- Make `SHORT` a rare exception for high-confidence, explicit tactical momentum only.
- Stop describing legacy `STABLE_SHORT`/`AGGRESSIVE_SHORT` as target holding horizons in deterministic prompts and strategy metadata.
- Extend default swing hold windows so the system is not biased toward 1~5 day exits by strategy name alone.
- Update focused tests and task artifacts.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Broker order placement or manual liquidation.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Not applicable

Plan implications:

- Adopt: treat `STABLE_SHORT`/`AGGRESSIVE_SHORT` as legacy execution/risk profile names, not desired holding horizon.
- Adopt: classify aggressive candidate hints only when surge and volume both support a moderate, non-overheated move.
- Adopt: lengthen default max hold days for stable and aggressive profiles to better align with swing/mid-horizon operation.
- Defer: database enum/strategy type rename, because that requires a wider migration and report compatibility plan.
- Reject: relying only on the prior `decide_trade_horizon` tweak, because several prompt/config surfaces still implied short-term trading.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python -m py_compile strategy/trade_horizon.py services/candidate_scoring_service.py services/deterministic_prompt_context_service.py strategy/stable_short.py strategy/aggressive_short.py strategy/base.py strategy/holding_policy.py core/config.py`
- `.venv313/bin/python -m pytest tests/strategy/test_trade_horizon.py tests/services/test_candidate_scoring_service.py tests/strategy/test_strategy_profiles.py tests/services/test_holdings_precheck_service.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
