# Decision Record

## Decision

1. Use a wider deterministic first pass because it is cheap and auditable, but keep the LLM subset bounded.
2. Align aggressive risk appetite with bull/theme momentum by widening `AGGRESSIVE_SHORT` hints only when positive momentum is confirmed by both surge and volume sources.
3. Exclude inverse/leveraged/cash-like/bond-like products from new automated BUY candidates and penalize defensive ETFs in aggressive mode.
4. Add minimum holding-time guards to strategic profit/review exits so MID/LONG positions are not closed within minutes.
5. Fix forward-return labeling priority so recent decisions can be benchmarked even when old rows are still waiting for market data.
6. Preserve trade notes through pending-confirm recovery because those notes carry horizon and active threshold metadata.
7. Restore persisted open-position exit thresholds on startup before scanning so a restart does not temporarily remove realtime stop/take controls.
8. Treat stop prices at/above average buy price as breakeven/profit-guard stops, not hard loss-protective stops. Apply MID/LONG minimum-hold guards to those exits unless the default loss stop is actually breached.

## Rationale

- Momentum evidence supports buying relative or time-series winners, but the cited horizons are not "minutes"; our current logs show many positions closed under one hour.
- Recent local performance shows `STABLE_SHORT` produced most of the 30-day loss while `AGGRESSIVE_SHORT` worked better in THEME. The scanner still defaults many candidates to `STABLE_SHORT`, even with `RISK_APPETITE=AGGRESSIVE`.
- Transaction-cost research favors lower turnover and buy/hold bands; our fast partial/trailing exits increase churn.
- Automated trading best practice supports layered controls. Stop-loss, broker reconciliation, position limits, and kill-switch behavior should stay active.
- Leveraged/inverse ETFs and cash/bond-like ETFs do not match the user's stated bull-market equity momentum intent.
- The live `082800` recovery showed that losing `notes` can reclassify a LONG position as SHORT in admin and exit logic fallbacks. That metadata needs to be treated as part of the trade contract, not transient UI detail.
- The live `459550` MID trade was closed at 10:21 for -45,000 KRW after a `HOLD` reanalysis raised `stop_loss` to 2,037, above its 2,035 average buy price. The fast holdings guard then treated that profit-guard threshold as a hard stop and sold at 2,010. That proves minimum-hold protection must distinguish loss stops from breakeven/profit stops.

## Deferred

- Full KRX daily OHLC backfill for accurate close-horizon decision benchmarking.
- Large backtest framework for all filter thresholds.
- Changing broker/order confirmation semantics.

## Risks

- Broader deterministic candidate logging may increase DB event volume.
- More aggressive momentum hints can increase drawdown if market regime flips quickly.
- Minimum holding-time guards can delay profitable exits; hard stop-loss and reconciliation exits are therefore preserved.
- Keyword-based product filtering can miss or over-filter unusual ETF names; this is intentionally conservative for new BUYs only.
- Startup threshold restoration only restores persisted AI stop/take/trailing values for confirmed open BUY rows; positions without persisted thresholds still rely on normal review/scan paths.
- A stop above cost basis can still execute after the minimum hold window or when the position breaches the horizon default loss stop; this preserves risk controls while preventing immediate profit-guard churn.
