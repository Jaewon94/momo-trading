# Brief

## Metadata

- Task ID: `2026-05-19-001-horizon-risk-rebalance`
- Created: `2026-05-19T17:26:15+09:00`
- Repo: `momo-trading`
- Title: Rebalance trading horizon and loss-streak recovery

## Goal

Allow controlled probation buys after loss streaks and reduce ultra-short chase bias by preferring MID/LONG horizons unless short-term criteria are exceptional

## Scope

In scope:

- Change live `LOSS_STREAK_RECOVERY_MODE` from `SHADOW` to `PROBATION` so a loss streak allows tightly capped recovery buys instead of full buy blocking.
- Fix code semantics so `SHADOW` is observation-only and does not block before LLM/risk review.
- Reduce ultra-short chase bias by classifying only exceptional, non-overheated momentum as `SHORT`; default uncertain/aggressive candidates to `MID`, and reserve `LONG` for high-confidence BULL/THEME candidates.
- Update focused tests and task artifacts.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Any broker order placement or manual liquidation.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Not applicable

Plan implications:

- Adopt: `PROBATION` with existing caps: max 1 recovery buy/day, max order 1,000,000 KRW, max position 0.5%, size multiplier 0.2, candidate change 2% to 10%.
- Adopt: keep short-term trading available only for qualified momentum; avoid late/overheated AI chase as the default path.
- Defer: adding fully separate multi-week/month portfolio strategy labels.
- Reject: leaving `SHADOW` as a hard block because it prevents recovery buys while presenting as observation mode.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python -m py_compile strategy/trading_guard.py agent/trading_agent.py strategy/trade_horizon.py services/candidate_scoring_service.py core/config.py`
- `.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py tests/strategy/test_trade_horizon.py tests/services/test_candidate_scoring_service.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
- Runtime settings check for `LOSS_STREAK_RECOVERY_MODE=PROBATION`
