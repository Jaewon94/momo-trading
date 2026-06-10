# Decision Record

## Decision

Increase final market-scan selected caps:

- SHORT: `8 -> 10`
- MID: `8 -> 12`
- LONG: `6 -> 12`

## Rationale

The deterministic scanner already reviews broad candidate pools:

- SHORT: 30 candidates
- MID: 60 candidates
- LONG: 100 candidates

Those candidates are sent to the market-scan LLM for comparative selection. The selected cap controls how many names proceed to deeper Tier1/Tier2 analysis and possible order evaluation.

The cap should be larger than before because MID/LONG scans run less often and can afford wider review. It should not be removed entirely because sending all candidates to Tier1/Tier2 would sharply increase latency, LLM cost, and automatic trading pressure.

This is not an LLM-only rule. The horizon split is enforced in code by `strategy/horizon_scan_policy.py`, then passed through market-scan selection and Tier1/Tier2 as `target_horizon_hint`. External research and official investor guidance support the broad distinction:

- FINRA treats frequent intraday trading as a separate risk pattern with margin/cost/rapid-loss considerations.
- FINRA Regulatory Notice 26-10 reinforces that intraday exposure should be monitored differently from ordinary non-intraday exposure.
- Market time-scale research supports using different windows for short-term and long-term signals.
- Momentum literature supports the idea that medium-horizon trend evidence can be useful, but with implementation risk and transaction-cost sensitivity.

The exact values `10/12/12` are operational defaults for this service. They are not presented as universal market constants.

## Deferred

- LONG still needs deeper financial/fundamental context beyond current news and price history.
- UI-specific horizon diagnostics can be added later if operators need a dedicated dashboard panel.

## Risks

- More selected candidates can increase Tier1/Tier2 LLM calls and the number of possible buy evaluations.
- Runtime still has a separate stale pending-order reconciliation issue; this change does not repair that operational state.
