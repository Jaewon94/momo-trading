# Decision Record

## Decision

Represent kill-switch runtime updates as explicit `runtime_effects` on the
TradingGuard result, then apply those effects through a small enforcement helper.

## Rationale

- The user concern is policy side effects being hidden across files.
- Kill-switch behavior must remain unchanged, but the runtime mutation should be
  visible in the result payload and testable as an effect.
- A small helper is lower risk than moving kill-switch behavior into a new
  runtime policy subsystem now.

## Deferred

- Broader runtime policy engine integration.
- Any tuning of kill-switch thresholds or guard modes.

## Risks

- This touches protected runtime-setting behavior. Tests must prove update calls
  are preserved only when enabled.
