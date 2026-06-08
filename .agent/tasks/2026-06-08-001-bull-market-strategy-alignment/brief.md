# Brief

## Metadata

- Task ID: `2026-06-08-001-bull-market-strategy-alignment`
- Created: `2026-06-08T09:09:13+09:00`
- Repo: `momo-trading`
- Title: Research and fix bull-market strategy alignment

## Goal

공식 자료와 논문 기반으로 불장/공격적 리스크/중장기 보유 의도에 맞게 후보 필터, 전략 배정, forward-return 계측, 조기청산 동작을 설계하고 필요한 코드를 수정·검증한다.

## Scope

In scope:

- Research-backed changes to deterministic candidate scoring and LLM scanner input breadth.
- Risk-appetite-aware strategy hinting for aggressive bull/theme participation.
- New-product filters/penalties for inverse, leveraged, cash-like, bond-like, and defensive ETF candidates.
- Forward-return labeling progress so old `WAITING_DATA` rows do not block recent decision benchmarking.
- Minimum holding-time guards for strategic profit/review exits while preserving protective stop-loss and reconciliation behavior.
- Profit-guard stop handling so a stop above cost basis is not treated as a hard loss-protective stop that bypasses MID/LONG minimum holding time.
- Soft stop-loss minimum holding-time guards so tight AI/active stops below cost basis do not close MID/LONG positions within minutes unless the horizon default hard stop is breached.
- Focused tests and runtime integrity checks after implementation.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, liquidation, broker credential changes, or destructive cleanup.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Jegadeesh/Titman momentum follow-up via NBER: momentum profits persisted beyond original sample, supporting relative-strength screening rather than pure random chasing.
- Moskowitz/Ooi/Pedersen time-series momentum via SSRN: trend persistence is documented at 1-12 month horizons, so a "mid/long" system should not churn most positions within minutes.
- Novy-Marx/Velikov transaction-cost taxonomy via NBER: transaction costs reduce anomaly profitability, and buy/hold spread is a key cost-mitigation technique.
- FCA/FIA automated-trading control guidance: keep pre-trade controls, monitoring, post-trade analysis, and kill-switch style safeguards; do not remove protective controls to improve returns.
- Kiwoom OpenAPI manual: order path supports limit/market/cancel primitives; application-level risk controls remain our responsibility.
- SEC leveraged/inverse ETF warning and Korean/FSS/KRX-related investor warnings: leveraged/inverse products target short periods and can diverge materially over longer holding horizons.
- Data.go.kr KRX stock price API note: daily KRX-derived data can lag; live decision benchmarking must not depend solely on next-day daily bars.

Plan implications:

- Adopt: broaden cheap deterministic candidate scoring to around 30 candidates, then let LLM analyze a smaller selected subset.
- Adopt: make aggressive risk appetite loosen AGGRESSIVE_SHORT hints only for confirmed positive momentum, not for inverse/defensive products.
- Adopt: hard-block inverse/leveraged/cash-like/bond-like products from new BUY candidates unless already held; de-prioritize defensive ETFs in aggressive mode.
- Adopt: add minimum age before strategic profit exits for MID/LONG positions; keep hard stop-loss and broker reconciliation paths active.
- Adopt: classify stop prices at or above cost basis as breakeven/profit protection, not hard loss stops; this prevents `HOLD` reanalysis from turning a MID/LONG position into an immediate stop-loss exit before minimum hold time.
- Adopt: classify tight stop prices below cost basis but above the horizon default loss threshold as soft stops; before the soft-stop minimum holding window, block those early exits while preserving the default hard stop.
- Adopt: change forward-return labeling order so recent events can be labeled even if old events remain missing data.
- Defer: full historical KRX daily-data ingestion/backfill; this is larger and may need API credentials/rate handling.
- Reject: removing risk controls or forcing all cash into positions just because the market is bullish.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python -m pytest tests/services/test_candidate_scoring_service.py tests/scheduler/test_forward_return_label_job.py tests/scheduler/test_scheduler_runtime_paths.py tests/strategy/test_trade_horizon.py -q`
- `python scripts/task_harness.py verify 2026-06-08-001-bull-market-strategy-alignment`
- Runtime health/integrity checks after restart if service is restarted.
