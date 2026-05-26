# Decision Record

## Decision

- Enabled supervised autonomous trading after preflight and runtime integrity were `OK`.
- On live integrity `FAIL`, immediately moved runtime back to safe mode: `TRADING_ENABLED=false`, `ORDER_SUBMISSION_MODE=READ_ONLY`, `AUTONOMY_MODE=SEMI_AUTO`, then explicitly stopped the scheduler.
- Kept the server running for observation/admin access instead of stopping the whole app.

## Rationale

- User explicitly requested enabling trading and ongoing checks.
- SEC/FINRA guidance for automated trading emphasizes documented risk controls, supervisory procedures, testing, monitoring, and controls that limit financial exposure.
- A lifecycle integrity `FAIL` means broker holdings and DB records may be inconsistent; continuing autonomous submission in that state is not acceptable operationally.
- The final checks recovered to `OK`, but the correct near-term posture is supervised read-only until the transient confirm/reconciliation window is reviewed.

## Deferred

- Code-level adjustment for transient `broker_untracked_holdings` during buy confirmation wait windows.
- Decide whether `BUY_ORDER_CONFIRM_WAIT_SEC_MODERATE=60` should be shortened or whether lifecycle integrity should tolerate matching fresh pending-confirm rows more explicitly.
- Re-enable autonomous trading only after operator review of this run and the final report.

## Risks

- Current final state is safe/read-only, not autonomous trading.
- One automated buy was confirmed for `307180` and one partial sell was confirmed for `487240`; market risk remains in the four open positions.
- `confirm_failed_count=9` is historical/terminal per lifecycle report, but should remain visible during future checks.
