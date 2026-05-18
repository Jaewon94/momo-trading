# Decision Record

## Decision

- Keep partially filled broker orders in `PENDING_CONFIRM` while `remaining_qty > 0`.
- Use `trade_results` as the source of truth for today's BUY attempt count.
- Attach effective dynamic risk limits to risk-check results so logs/details no longer imply the static limit when AI tuning is active.

## Rationale

- A broker order with remaining quantity is not settled. Marking it `CONFIRMED` removes the DB pending row and creates `broker_only` drift.
- The active trading path records order lifecycle in `trade_results`; the legacy `orders` table can be empty, producing `0/30` risk logs even after real BUY attempts.
- `HOLDING_SYNC` rows are reconciliation artifacts, not new risk-consuming BUY attempts.

## Deferred

- Existing live order `0067887` remains a protected operational repair. Code fixes prevent recurrence but do not mutate current broker/DB state without approval.
- Full historical cleanup of `CONFIRM_FAILED`, unpaired SELL, and neutral close rows remains separate from this code-contract fix.

## Risks

- Pending partial fills may keep a symbol/order blocked until broker 잔량 fully fills, is cancelled, or is explicitly repaired.
- Current runtime integrity can still report the already-existing broker-only order until a protected DB or broker action is approved.
