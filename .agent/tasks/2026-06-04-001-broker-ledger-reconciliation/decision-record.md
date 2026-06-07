# Decision Record

## Decision

Patch the confirmation path, not the trading strategy.

## Rationale

The live check showed that the service was running, but `SG세계물산(004060)` was absent from broker holdings while `trade_results` still exposed it as an open BUY lot. The relevant code already has read-only lifecycle detection and manual DB reconciliation, so the unsafe part is not strategy selection but SELL bookkeeping when broker status lookup lags.

The intraday holdings-review path should use the same scheduler SELL tracking helper as other scheduler sell paths, because that helper creates a `PENDING_CONFIRM` SELL audit row before confirmation. SELL holding-delta inference should also read fresh broker holdings after cache invalidation, including the timeout path.

## Deferred

- Live DB repair for the current SG Global row.
- Broker order cancellation/replay.
- Strategy threshold/risk appetite changes.

## Risks

- This touches protected broker reconciliation behavior, so verification must include focused agent/scheduler tests and read-only runtime integrity.
- Even after the code fix, the already-existing live DB mismatch may remain until a confirmed manual reconciliation is applied.
