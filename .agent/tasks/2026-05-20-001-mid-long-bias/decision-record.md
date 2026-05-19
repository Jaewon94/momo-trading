# Decision Record

## Decision

- Treat `STABLE_SHORT` and `AGGRESSIVE_SHORT` as legacy execution/risk profile names, not target holding horizons.
- Make `MID` the default horizon and `LONG` the preferred horizon for high-confidence bull/theme setups without tactical spike/drop triggers.
- Allow `SHORT` only for explicit tactical momentum: aggressive profile, `PRICE_SURGE`/`VOLUME_SPIKE`, bull/theme regime, 5~10% move, and confidence at least 0.78.
- Candidate scoring now marks `AGGRESSIVE_SHORT` only when both surge and volume-rank evidence exist, move is 6~10%, score is at least 50, and news pressure is low.
- Holding policy now reads `trade_horizon` from trade notes first. Runtime max hold windows are SHORT 5 days, MID 15 days, LONG 30 days; legacy fallback windows are STABLE 15 and AGGRESSIVE 10.

## Rationale

- LLM analysis and broker confirmation latency are poorly matched to broad ultra-short chasing.
- The previous change narrowed `SHORT` classification, but prompts, strategy descriptions, and hold-day defaults still implied short-term trading.
- Horizon should control risk/exit/holding policy more than the legacy strategy type name.
- Keeping legacy strategy type names avoids a DB/report migration while changing the actual operating semantics.

## Deferred

- Renaming DB strategy types is deferred because it requires a broader migration and reporting compatibility plan.

## Risks

- Longer hold windows can keep losing positions open longer if stop-loss/news/AI review gates fail. Runtime integrity and holding review paths must stay green.
- Stricter tactical classification can miss fast intraday winners. This is intentional because the user's priority is mid/long-horizon consistency over short-term chase frequency.
- `.env` is local and ignored by git, so `.env.example` was updated for future consistency but this machine also required direct `.env` adjustment and restart.
