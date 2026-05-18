# Decision Record

## Decision

- Keep true broker/DB drift as FAIL: broker-only pending orders and DB open BUY lots absent from broker holdings remain blocking integrity failures.
- Reclassify terminal/history rows as informational: `CONFIRM_FAILED` and neutral holding reconciliation closes no longer drive WARN/FAIL.
- Reclassify partial-fill pending as WARN in the runtime gate because it is a live order state, not settled drift.
- Prevent future holdings backfill when broker pending orders exist for the symbol.
- Add lifecycle detection for broker holdings that exceed DB open BUY quantity when there is no matching DB pending confirm.
- Classify broker pending orders that still match a non-pending DB trade by `order_id` as a dedicated FAIL (`broker_linked_non_pending`) instead of hiding them under generic broker-only drift.
- When recovering a disappeared BUY pending from holdings, infer only the holding delta over already-confirmed DB open BUY quantity, capped by requested quantity.
- Do not show an old order error as a current operations WARN forever; only order errors inside the last 24 hours should affect `/system/status` operations health.
- When a Kiwoom SELL pending has no broker pending order and broker holding quantity is already greater than or equal to DB open BUY quantity, mark it as stale failed instead of falling through to a cancellation attempt.
- Recheck Kiwoom SELL orders that initially report `filled_qty=0` with remaining quantity before cancellation; increase the default SELL confirmation wait from 3 seconds to 10 seconds.

## Rationale

- The 27 reported unpaired SELLs were already reflected on BUY lots by the live sell confirmation/repair path; treating them as actionable would double-apply closes.
- `CONFIRM_FAILED` rows are canceled/no-fill/recovery terminal records. Active pending/order inconsistencies are checked separately.
- Neutral closes are operational reconciliation artifacts excluded from performance, not live positions.
- The active `0067887` broker pending buy is genuinely broker-only in DB and can keep filling unless canceled or explicitly repaired.
- The 30 stale open BUY lots across 20 symbols are genuinely absent from broker holdings and should be neutral-closed only with explicit runtime DB approval.
- `066430` currently has broker quantity 53 but DB open quantity 52; this is now separately detected as DB-untracked broker holding.
- Later root-cause check showed `0067887` is a live partial-fill order: broker filled quantity advanced to 60 with remaining quantity 3190 while DB still had only 52 open BUY shares. The original pending link was lost when the first partial fill was marked `CONFIRMED`; subsequent fills were represented through holding sync backfills instead of one durable order lifecycle record.
- The current runtime now correctly exposes `0067887` as `broker_pending_order_linked_to_non_pending_db_trade`: broker pending remains live, while the DB row with the same order id is already `CONFIRMED` for only 8 shares.
- Delta-based BUY recovery avoids turning a partially filled/cancelled large order into a duplicate full holding when the symbol already has confirmed open lots.
- The 2026-05-15 order error was historical after 2026-05-18 restart; keeping it as a current WARN made a healthy system look degraded after integrity was repaired.
- The 2026-05-18 `011000` 1320-share SELL pending was already reflected in broker/DB holdings after later reconciliation and partial sell recording. A second cancellation attempt would not improve consistency and could add unnecessary broker side effects.
- The 2026-05-18 `011000` 1188-share protective SELL failed because the confirmation path treated an early zero-fill/remaining-quantity status as terminal after only 3 seconds. A bounded retry keeps protective sells alive long enough for Kiwoom status/holding data to catch up while still cancelling if no fill appears.

## Deferred

- Continue monitoring live cycles for any new `PENDING_CONFIRM` that does not settle after broker/account refresh.

## Risks

- Future broker/API throttling can still create short-lived pending/holding timing gaps; the runtime integrity gate should be checked after a refresh cycle before treating those as settled drift.
