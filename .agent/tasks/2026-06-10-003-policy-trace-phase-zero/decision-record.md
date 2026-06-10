# Decision Record

## Decision

Implement Phase 0 as trace-only infrastructure. Existing policy functions keep
their current control flow and side effects; adapters translate their outputs to
`PolicyTrace` dictionaries for logs and metadata.

## Rationale

- This preserves trading behavior while making scattered policy decisions
  visible in one schema.
- It keeps broker/order placement protected because no order decision branch is
  widened or loosened.
- It creates the foundation needed before moving logic behind a central engine.

## Deferred

- Settings catalog and registry completeness checks.
- Moving gate calls behind `TradingPolicyEngine`.
- Removing `TradeSignal` mutation from risk/exposure code.
- Any live runtime setting update.

## Risks

- Trace metadata increases activity log detail size.
- Some paths may not yet be covered in Phase 0; uncovered owners should be
  listed in the final report rather than silently claimed complete.
