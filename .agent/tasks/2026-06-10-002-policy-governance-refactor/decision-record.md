# Decision Record

## Decision

Create a behavior-preserving refactor plan before touching trading logic. The
plan introduces an internal `TradingPolicyEngine` contract, not an external
policy engine, and requires a settings catalog plus policy trace before moving
logic.

## Rationale

- The current code already has multiple legitimate safety layers. Removing them
  would be risky; centralizing ownership and trace is safer.
- Official policy governance patterns separate policy decision from enforcement.
  That maps well to `TradingPolicyEngine` as PDP and `TradingAgent` /
  `DecisionMaker` as PEP.
- Algorithmic trading guidance emphasizes change management, validation, and
  supervisory controls. A docs-only plan is appropriate before behavior changes.
- Runtime settings are long-lived and can override code defaults, so settings
  need owner/risk/test metadata.

## Deferred

- OPA or another external policy engine. Internal typed contracts are enough for
  the current repo and avoid extra runtime dependency.
- Admin UI metadata for policy owner/risk. Do this after `settings_catalog.py`
  exists.
- Any threshold tuning or broker-facing behavior change.

## Risks

- `TradingAgent` contains many policy calls and must be split in small parity
  steps.
- Some current policies perform DB/runtime side effects. Phase 0 should trace
  them first; Phase 3 can separate side effect enforcement.
- Event-driven stop/take-profit sell paths need special care because they are
  not purely LLM decisions.
