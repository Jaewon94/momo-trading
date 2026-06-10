# Decision Record

## Decision

Add a `TradingPolicyEngine` facade that wraps the existing gate services and
trace adapter functions, while keeping `TradingAgent` and `DecisionMaker`
responsible for orchestration and enforcement.

## Rationale

- The current risk is policy drift across files, not one threshold value.
- A facade creates a single policy entry point without moving behavior-changing
  logic yet.
- Keeping existing service objects injectable preserves current tests and
  runtime dependency wiring.

## Deferred

- Removing direct `TradeSignal` mutation from risk/exposure policies.
- Making the policy engine the sole source of runtime setting validation.
- Generated policy registry documentation.

## Risks

- This is still a wrapper phase; duplicated enforcement code remains until
  Phase 3.
- Order submission is a protected area, so this task must keep order request
  construction and broker calls unchanged.
