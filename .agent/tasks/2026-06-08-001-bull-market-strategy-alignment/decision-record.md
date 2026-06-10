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
9. Treat tight loss stops below average buy price but above the horizon default loss threshold as soft stops. Apply a short horizon-specific minimum hold before honoring those stops, while still allowing the default hard stop immediately.
10. Keep the consecutive-loss recovery guard in `PROBATION` mode, but allow up to 50 probation BUYs per trading day. The daily count already resets by date, so this preserves the warning/reduced-size behavior without blocking aggressive-mode participation after a small number of early losses.
11. Make intraday holdings-review prompts explicitly horizon-aware. The prompt must show `trade_horizon`, max hold days, minimum hold guards, and state that `STABLE_SHORT`/`AGGRESSIVE_SHORT` are legacy execution/risk profiles, not holding-period labels.
12. Replace intraday MID/LONG minimum-hold defaults with horizon-consistent non-protective exit windows: MID 1440 minutes and LONG 2880 minutes for review exits, profit/partial/trailing exits, and soft stops. SHORT remains tactical. Hard default stop-loss breaches remain immediate.
13. Widen MID/LONG default exit bands and make default stop breaches staged: MID stop/take -7%/+12%, LONG -10%/+18%, MID first stop breach sells 50%, LONG first stop breach sells 33%, and deep breaches still allow full exit. ADD_BUY must satisfy a pullback-above-stop candidate rule before re-entering the full analysis/risk pipeline.

## Rationale

- Momentum evidence supports buying relative or time-series winners, but the cited horizons are not "minutes"; our current logs show many positions closed under one hour.
- Recent local performance shows `STABLE_SHORT` produced most of the 30-day loss while `AGGRESSIVE_SHORT` worked better in THEME. The scanner still defaults many candidates to `STABLE_SHORT`, even with `RISK_APPETITE=AGGRESSIVE`.
- Transaction-cost research favors lower turnover and buy/hold bands; our fast partial/trailing exits increase churn.
- Automated trading best practice supports layered controls. Stop-loss, broker reconciliation, position limits, and kill-switch behavior should stay active.
- Leveraged/inverse ETFs and cash/bond-like ETFs do not match the user's stated bull-market equity momentum intent.
- The live `082800` recovery showed that losing `notes` can reclassify a LONG position as SHORT in admin and exit logic fallbacks. That metadata needs to be treated as part of the trade contract, not transient UI detail.
- The live `459550` MID trade was closed at 10:21 for -45,000 KRW after a `HOLD` reanalysis raised `stop_loss` to 2,037, above its 2,035 average buy price. The fast holdings guard then treated that profit-guard threshold as a hard stop and sold at 2,010. That proves minimum-hold protection must distinguish loss stops from breakeven/profit stops.
- The remaining early-exit risk is a tight AI/active stop below cost basis, for example a MID entry at 10,000 with active stop 9,900. A 1-3% early loss can be ordinary intraday noise for a mid/long thesis, so it should not bypass the thesis window unless the MID default hard stop, currently -4%, is actually breached.
- On 2026-06-08, `RISK_APPETITE=AGGRESSIVE` conflicted with `LOSS_STREAK_RECOVERY_MODE=PROBATION` and `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS=2`: after three early BUYs, every candidate reached LLM/risk review but was blocked by the probation daily cap. Raising the cap to 50 matches the aggressive-mode intent better than disabling the entire recovery guard.
- The intraday holdings-review prompt already received holdings payloads that included `trade_horizon`, but the prompt text did not display that field and only displayed `strategy_type`. This could lead the LLM to interpret `STABLE_SHORT`/`AGGRESSIVE_SHORT` as short-horizon labels even though the runtime exit policy uses `notes.trade_horizon`.
- A 180-minute MID profit guard is an intraday trading rule, not a medium-horizon contract. Keeping deterministic hard-risk controls is still necessary, but non-protective exits must not let code rules bypass the LLM's medium/long thesis.
- SEC/Investor.gov warns that stop orders and trailing stops can be triggered by short-term intraday moves and may execute away from the trigger price. For MID/LONG, tighter stops create churn and worse realized exits without necessarily proving thesis failure.
- The code already uses `RISK_PER_TRADE_PCT` volatility/stop-distance sizing. Widening MID/LONG stops therefore reduces position size at entry instead of silently increasing per-trade account risk.
- A single all-or-nothing stop is too binary for medium/long positions in a volatile market. Staged loss reduction limits exposure while still allowing the remaining thesis to survive shallow breaches.
- ADD_BUY exists in the LLM action schema, but buying more solely because price fell is averaging down. Requiring the existing scale-in candidate condition makes it a controlled pullback entry, not automatic 물타기.

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
- A soft stop below cost basis can also execute after its configured minimum hold window. This may increase interim drawdown compared with the previous tighter behavior; the default hard stop remains the emergency boundary.
- A 50-trade probation cap can increase turnover and intraday loss if the model keeps selecting weak candidates. Daily drawdown, account-equity drawdown, position sizing, order confirmation, and hard stop controls remain active.
- Prompt improvements reduce LLM horizon confusion but do not remove hard stops, severe-news exits, or max-hold review exits. The LLM can still recommend SELL when the thesis is clearly broken; runtime minimum-hold guards remain the final safety net for non-hard-stop exits.
- Longer MID/LONG windows increase overnight exposure and may forgo same-day partial gains. This is intentional for the stated medium/long bias; hard default loss stops, severe-news exits, broker reconciliation, duplicate-sell locks, and kill-switch controls remain active.
- Wider MID/LONG stops can allow larger mark-to-market drawdown on individual holdings. Position sizing, account drawdown guard, staged partial stop-loss, and deep-breach full exits are the compensating controls.
- Partial stop-loss leaves residual position risk after the first loss reduction. Remaining lots are marked so deterministic code does not immediately sell the rest for the same shallow breach, but deep breaches and AI thesis-break exits still close the position.
- ADD_BUY gating may skip some successful V-shaped rebounds. This is intentional to avoid averaging down broken positions.
