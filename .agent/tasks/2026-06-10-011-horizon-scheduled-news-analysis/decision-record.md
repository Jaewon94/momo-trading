# Decision Record

## Decision

Implement horizon-scheduled analysis by extending the existing trading cycle with a `scan_horizon` mode.

- Frequent existing scans run as SHORT.
- A daily scheduled scan runs as MID.
- A weekly scheduled scan runs as LONG.
- Scanner filters, candidate count, news pressure, news context, and daily candle depth are horizon-aware.
- MID/LONG scanner hints override the candidate trade horizon for BUY cost/Tier2 review; SHORT/default candidates still use the existing trade-horizon decider to avoid forcing excess short-term exits.
- All BUY/SELL execution still flows through the current LLM Tier1/Tier2, policy engine, risk gates, and order submission guards.

## Rationale

- The user wants pre-LLM filtering and news context to differ by intended holding horizon.
- Reusing `trading_agent.run_cycle` avoids introducing a second order path.
- Separate schedules prevent long-horizon analysis from competing with short-cycle latency on every intraday scan.
- Horizon scan profiles keep schedule/filter/news assumptions in one place instead of spreading constants through scanner, scheduler, and prompts.
- Existing news ingestion is reused. This phase changes how far back and how many items each horizon passes to LLM; it does not introduce a new news provider.

## Deferred

- True structured-output split of SHORT/MID/LONG analysts.
- DART/fundamental context ingestion for LONG.
- Separate provider/model settings by horizon.
- Any broker/runtime DB repair.

## Risks

- MID/LONG scheduled scans can increase BUY opportunity frequency; order/risk gates must stay authoritative.
- LONG still lacks financial statement ingestion in this phase, so LONG is better than before but not yet a full fundamental thesis engine.
- Existing runtime integrity has a stale pending-order issue unrelated to this implementation.
