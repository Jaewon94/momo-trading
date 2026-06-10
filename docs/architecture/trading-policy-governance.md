# Trading Policy Governance

This document defines how trading policy layers should be ordered and reviewed so
new strategy changes do not silently conflict with older controls.

Detailed refactor design:
[Trading Policy Engine Refactor Plan](trading-policy-engine-refactor-plan.md)

Before changing trading policy code, prompts, or runtime settings, use:
[Trading Policy Change Checklist](../workflows/trading-policy-change-checklist.md)

## Policy Priority

1. Hard safety controls
   - Kill switch, account drawdown, broker/session availability, post-liquidation
     buy block, and operator-disabled modes.
   - These controls can block BUY/SELL execution regardless of model output or
     risk appetite.
2. Broker and market constraints
   - Buying power, orderable quantity, tick/price limits, market session rules,
     pending order reconciliation, and provider errors.
   - These controls can reduce quantity or block execution after internal checks.
3. Portfolio risk manager
   - Position cap, order cap, minimum cash policy, risk/reward, volatility sizing,
     daily trade limits, and trading guard warnings.
   - This layer owns final internal quantity reduction before broker checks.
4. Exposure alignment
   - Converts an operator intent such as `RISK_APPETITE=AGGRESSIVE` into a target
     exposure behavior when market regime and confidence allow it.
   - This layer may raise an already-approved BUY quantity, but it must run before
     the risk manager and must not bypass hard safety or broker checks.
5. LLM and deterministic strategy decision
   - Produces BUY/HOLD/SELL intent, confidence, horizon, and initial sizing.
   - Model output is advisory until deterministic policy layers approve it.
6. Scanner and pre-analysis filters
   - Reduce the candidate universe and attach structured evidence for later
     decisions.
   - These filters should not own final portfolio exposure or order sizing.

## Ownership Rules

- Risk appetite is an intent, not a complete policy. It may select limits and
  targets, but a named downstream layer must own each concrete behavior.
- Target exposure belongs to exposure alignment.
- Final internal order size belongs to the risk manager.
- Final executable order size belongs to broker buying-power/orderability checks.
- Holding period and forced-exit behavior belong to holding/exit policy.
- Candidate breadth belongs to scanner policy.
- Any layer that mutates action, quantity, price, horizon, or thresholds must
  emit structured metadata with the previous value, final value, owner layer,
  and reason. Silent mutation is treated as a policy bug.

## Change Protocol

Every change that touches buy/sell thresholds, risk profile behavior, holding
horizon, order placement, end-of-day handling, or broker reconciliation should:

- Name the affected policy owner in the task brief or decision record.
- State whether the change can increase order size, decrease order size, block
  orders, or force/accelerate sells.
- Add or update tests at the policy-owner layer.
- Preserve downstream hard safety checks unless the task explicitly approves a
  protected behavior change.
- Add activity-log or trade-note metadata when a later review would need to know
  why a quantity or action changed.
- When a policy layer mutates a `TradeSignal` directly, its return value must
  still describe the mutation. Callers should not have to infer changes by
  comparing object state before and after the call.
- Keep the policy owner, priority, runtime settings, and focused tests aligned
  with the refactor plan. If a new setting or gate cannot be assigned to an
  owner, treat that as a design gap before implementation.

## Runtime Settings Review

Runtime settings can outlive code changes. After restart or policy tuning, compare
live runtime settings with intended defaults for:

- risk appetite and dynamic caps
- cash/exposure targets
- daily trade/probation limits
- holding horizon and exit thresholds
- broker/session mode

If live settings conflict with a new policy, prefer an explicit runtime update and
record the source of the override rather than hiding the mismatch in code.

## Conflict Diagnosis Checklist

When behavior looks wrong, inspect the decision path in this order:

1. Was the candidate filtered out before LLM analysis?
2. Did the LLM return BUY/HOLD/SELL and what initial quantity?
3. Did exposure alignment change the BUY quantity?
4. Did the risk manager reduce or block the order?
5. Did cash reservation reduce or block the order within the cycle?
6. Did broker buying power/orderability reduce or block the order?
7. Did execution fail, partially fill, or remain pending?
8. Did runtime settings override the expected code defaults?

The answer should be visible in structured metadata or activity logs. If it is not
visible, observability should be fixed before tuning thresholds again.
