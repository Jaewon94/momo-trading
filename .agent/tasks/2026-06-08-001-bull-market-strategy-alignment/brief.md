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
- Horizon-consistent default stop/take/profit/trailing thresholds so MID/LONG positions are not managed with intraday-width exits.
- Staged MID/LONG loss reduction so the first default stop breach can reduce risk partially instead of always liquidating the full position.
- ADD_BUY guardrails so "buying the dip" requires a valid MID/LONG pullback above the stop, not blind averaging down after thesis damage.
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
- FINRA frequent intraday trading guidance: frequent intraday trading targets rapid small price moves, carries higher costs, and short-term profit capture is generally less reliable than long-term investing.
- Time-horizon practice references: medium/intermediate horizons are not measured in hours. Even trading-oriented "swing" usage implies at least multi-day intent, while broad investing references use years for intermediate/medium horizons.
- Time-series momentum research in China and deep momentum research both emphasize explicit look-back/holding periods and turnover/cost control, which conflicts with unintentional same-day churn.
- Algorithmic-trading controls research supports keeping automated hard-risk controls, tests, and simulations while narrowing non-protective exit authority.
- SEC/Investor.gov stop-order bulletin: stop and trailing-stop orders can be triggered by short-term intraday price moves, and execution price can deviate from the stop in fast markets. This supports avoiding overly tight MID/LONG stop placement.
- Stop/take-profit optimization research for autonomous trading agents: exit policy materially affects risk-adjusted performance and should be explicit/testable rather than incidental defaults.
- Position-sizing research for volatile algorithmic trading: volatile regimes are better controlled through position sizing and risk budgets, not only tighter stop distances.
- Dollar-cost/value-averaging references: staged buying can reduce timing regret but creates cost/cash-drag and must not be confused with averaging down a broken individual-stock thesis.

Plan implications:

- Adopt: broaden cheap deterministic candidate scoring to around 30 candidates, then let LLM analyze a smaller selected subset.
- Adopt: make aggressive risk appetite loosen AGGRESSIVE_SHORT hints only for confirmed positive momentum, not for inverse/defensive products.
- Adopt: hard-block inverse/leveraged/cash-like/bond-like products from new BUY candidates unless already held; de-prioritize defensive ETFs in aggressive mode.
- Adopt: add minimum age before strategic profit exits for MID/LONG positions; keep hard stop-loss and broker reconciliation paths active.
- Adopt: classify stop prices at or above cost basis as breakeven/profit protection, not hard loss stops; this prevents `HOLD` reanalysis from turning a MID/LONG position into an immediate stop-loss exit before minimum hold time.
- Adopt: classify tight stop prices below cost basis but above the horizon default loss threshold as soft stops; before the soft-stop minimum holding window, block those early exits while preserving the default hard stop.
- Adopt: raise MID/LONG non-protective exit windows from intraday minutes to calendar-day style guards: MID 1440 minutes and LONG 2880 minutes for review exits, profit/partial/trailing exits, and soft stops. SHORT remains tactical.
- Adopt: expose the minimum-hold settings through runtime settings so the operator can verify or adjust the policy without a code change.
- Adopt: widen default MID/LONG hard stop-loss to -7%/-10% and corresponding take-profit to +12%/+18%, with partial profit/trailing activation lifted to match. The existing risk-per-trade sizing reduces quantity when the stop distance widens.
- Adopt: for MID/LONG default stop breaches, sell an initial partial amount (MID 50%, LONG 33%) unless the breach is deep enough for full exit. Mark remaining lots with `PARTIAL_STOP_LOSS_DONE` so the next check cannot immediately finish the liquidation for the same shallow breach.
- Adopt: keep full liquidation for SHORT, deep stop breaches, broker reconciliation, manual sells, and thesis-breaking AI SELL decisions.
- Adopt: gate ADD_BUY through the existing scale-in candidate rule: MID/LONG only, configured pullback band, current price above active stop, then normal Tier1/Tier2/risk checks. Do not auto-buy simply because a position is down.
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
