# Brief

## Metadata

- Task ID: `2026-05-20-002-scanner-probation-alignment`
- Created: `2026-05-20T10:10:45+09:00`
- Repo: `momo-trading`
- Title: Align scanner with probation and mid long bias

## Goal

Make candidate scanning and strategy selection produce probation-compatible mid/long-biased buy candidates instead of repeatedly surfacing overheated short-term movers that final risk guard rejects.
Also make loss-streak PROBATION behave as a reduced-size recovery lane rather than a near-hard buy lock, while preserving the final order/risk guard.

## Scope

In scope:

- Align market-scan prompt language with the current mid/long-biased policy.
- Align Tier1 stock-analysis prompt language with the current mid/long-biased policy.
- Make deterministic candidate scoring penalize overheated buy candidates before LLM selection.
- Enforce loss-streak PROBATION buy-candidate change-rate limits after LLM selection.
- Relax over-sticky loss-streak PROBATION blockers: allow recovery entries while already holding, downgrade repeated-loss pattern and a single weak intraday component to warnings, and keep hard blocks for daily cap, overheat/under-min-change, and compound weak intraday signals.
- Align the protected live runtime setting `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS` with the code default after explicit user approval.
- Restore persisted open-position AI exit thresholds into the in-memory event detector after intraday restart, so existing holdings do not fall back to default stop/take rules.
- Add focused tests for scanner policy and candidate scoring behavior.
- Add focused tests for the revised loss-streak PROBATION guard behavior.

Out of scope:

- Unrelated trading behavior changes beyond scanner/probation consistency and loss-streak recovery-lane calibration.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Removing the final trading guard just to force orders through.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- FINRA algorithmic trading guidance: supervision/control programs should include risk assessment, software development/testing, and post-change trading activity review.
- FINRA Regulatory Notice 15-09: algorithmic strategy changes should be reviewed, tested before deployment, and monitored after implementation.
- CFA Institute risk management refresher: risk tolerance, risk budgeting, position limits, stop-loss limits, and feedback loops should drive action.

Plan implications:

- Adopt: keep final order/risk guard strict and move incompatible candidates out earlier in the scanner path.
- Adopt: use deterministic policy enforcement around LLM output because prompts alone are not reliable enough for protected trading behavior.
- Adopt: keep a consecutive-loss risk control, but avoid a self-reinforcing lock where only a closed winning trade can reset the state while the guard prevents new reduced-risk opportunities.
- Defer: broader factor model or portfolio optimizer changes.
- Reject: increasing the PROBATION max-change threshold above 10% as the first fix, because that conflicts with the mid/long bias and recent overheat losses.

## Completion Criteria

- Required changes are implemented.
- Focused verification covers candidate scoring, market scanner policy, and prompt alignment.
- Focused verification covers softened loss-streak PROBATION behavior.
- Live runtime setting and live LLM prompt evidence match the intended mid/long recovery policy.
- Existing open positions keep their persisted AI stop/take/trailing thresholds after restart.
- Runtime is restarted and read-only health/integrity checks are run after restart.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python -m pytest tests/services/test_candidate_scoring_service.py tests/agent/test_market_scanner.py -q`
- `python -m pytest tests/strategy/test_trading_guard.py -q`
- `python scripts/change_harness.py <changed paths>`
- `python scripts/task_harness.py verify 2026-05-20-002-scanner-probation-alignment`
- `python scripts/check_runtime_integrity.py --days 7`
