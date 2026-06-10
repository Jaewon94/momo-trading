# Decision Record

## Decision

Split trade threshold policy into pure calculation and explicit enforcement,
while retaining `_apply_trade_thresholds` as the compatibility wrapper used by
existing callers.

## Rationale

- Phase 3 requires mutation/effect boundaries to be visible.
- Threshold calculation can be made pure without changing caller behavior.
- Keeping the wrapper prevents broad call-site churn and reduces order/exit
  behavior risk.

## Deferred

- Runtime kill-switch side-effect extraction.
- Changing stop-loss/take-profit/trailing-stop formulas.

## Risks

- Threshold values directly affect event-driven exits, so this task must not
  tune the formulas.
- Existing tests should continue to assert the same calculated values.
