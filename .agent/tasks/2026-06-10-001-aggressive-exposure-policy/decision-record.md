# Decision Record

## Decision

1. Treat `RISK_APPETITE=AGGRESSIVE` as an intent, not a final position size.
2. Add an explicit exposure-alignment layer that owns the "use more cash in bullish regimes" policy.
3. Run exposure alignment only after a BUY has already passed Tier1/Tier2, and before the existing risk manager and broker checks.
4. Keep hard safety authority with drawdown/kill-switch/trading-guard/risk-manager/broker gates.
5. Add activity-log events for aggressive exposure alignment, risk-manager quantity adjustment, and broker buying-power quantity adjustment.
6. Persist exposure-alignment metadata in trade notes so future reviews can explain why a position was sized up or not.
7. Treat risk-manager quantity mutation as a first-class policy decision: if trading guard, probation, volatility sizing, cash, or position caps change quantity, the result must include `previous_quantity`, `adjusted_quantity`, `adjustments`, and `warnings`.

## Rationale

- The current system has many valid safety layers, but no single owner for target market exposure. This made "aggressive" mostly mean "do not require cash," not "try to reach a measured exposure target."
- AI risk tuning sets daily/order caps, but it does not force approved signals to use those caps.
- Tier2 can approve a BUY while still suggesting a small quantity. Without a floor policy, a high-cash account can stay underexposed indefinitely.
- Probation, volatility sizing, account drawdown, buying-power, and broker submission are safety controls. They should remain later in the chain and can still reduce or block an exposure-raised quantity.
- Quantity changes were not observable enough: Tier2 could show 300 shares while the final order showed 150 shares. Logging each adjustment stage prevents future ambiguity.
- Live restart validation exposed an additional ambiguity: trading guard reduced an exposure-raised BUY from 4,211 shares to 2,105 shares through a size multiplier, but the risk result still reported `adjusted_quantity: null`. This made a valid safety reduction look like an unexplained conflict. The risk manager now reports these mutations explicitly.

## Deferred

- Admin UI controls for the new aggressive exposure settings.
- Backtesting target exposure bands across market regimes.
- Changing absolute system caps (`ABS_MAX_SINGLE_ORDER_KRW`, `ABS_MAX_POSITION_PCT`).

## Risks

- Approved BUYs in BULL/THEME regimes can become larger than the LLM initially requested, increasing mark-to-market volatility.
- If the market regime classifier is too optimistic, exposure alignment can add risk in a false bull/theme regime.
- Risk manager can still shrink the exposure-raised quantity, which may look like another conflict unless the logs are reviewed by stage.
- Runtime settings persisted from older policies can still override code defaults; operational checks should compare live settings to intended policy values after restart.
- Aggressive exposure alignment is progressive, not an all-cash deployment policy. If Tier1/Tier2 approve only a few BUYs, cash can remain high even in AGGRESSIVE mode.
