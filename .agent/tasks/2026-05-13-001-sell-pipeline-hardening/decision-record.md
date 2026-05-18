# Decision Record

## Decision

- Implement the first sell-pipeline hardening step inside the existing
  scheduler holdings check path instead of introducing broker-native bracket
  orders in this task.
- Keep AI holdings review as a slower contextual layer; add deterministic
  horizon-aware exit checks for faster risk/profit protection.

## Rationale

- The current broker adapter path already handles duplicate sell locks and fill
  confirmation. Reusing it limits order-placement blast radius.
- Official order guidance highlights market/stop execution-price risk, so the
  app should protect profits before forced exits become urgent.
- Bracket/OCO behavior is a good model, but submitting native child orders needs
  broker capability work and should not be mixed into this change.

## Deferred

- Broker-native OCO/bracket order support.
- Full buy-pipeline Tier1 LLM replacement.
- UI panels for new sell-stage observability.

## Risks

- Exit rules can increase churn if thresholds are too tight. Tests must cover
  short vs mid/long behavior, and defaults should remain conservative.
- Scheduler changes touch live trading behavior; no live orders are triggered
  during verification.
