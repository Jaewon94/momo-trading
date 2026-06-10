# Decision Record

## Decision

Move quantity enforcement out of policy evaluators where the caller already has
an enforcement point. `RiskManager.check` should return adjusted quantity and
effects, while `TradingAgent` applies the quantity before broker/order checks.
Aggressive exposure alignment should likewise return a decision and let the buy
path enforce the final quantity.

## Rationale

- Central policy governance needs clear PDP/PEP separation.
- The existing caller already applies `risk_result["adjusted_quantity"]`, so
  removing risk-manager mutation is behavior-preserving.
- Exposure alignment is easier to trace when evaluation and enforcement are
  distinct, while still preserving the same final quantity.

## Deferred

- Runtime kill-switch side-effect extraction.
- Trade threshold/event-detector enforcement split.
- Full pure evaluator conversion for all policy owners.

## Risks

- The changed code touches order sizing, so parity tests and runtime integrity
  checks are required.
- External callers that relied on `RiskManager.check` mutating the signal must
  now use `adjusted_quantity`; repo search found the trading agent already does
  this.
