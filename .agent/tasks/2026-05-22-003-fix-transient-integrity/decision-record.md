# Decision Record

## Decision

- Treat fresh DB `PENDING_CONFIRM` rows as in-flight broker/DB reconciliation grace:
  - fresh BUY pending can cover temporary broker holdings above DB confirmed open quantity.
  - fresh SELL pending can cover temporary broker holdings below DB confirmed open quantity.
- Keep stale pending-confirm mismatches as `FAIL`.

## Rationale

- Today's false `broker_untracked_holding` happened while a buy order was inside the configured confirmation window.
- Broker pending orders can disappear before DB confirmation finalizes because the order is already filled or cancelled.
- The existing check only tolerated extra holdings when both broker pending and DB pending existed; that was too strict for real broker timing.
- A bounded grace window preserves safety: transient state becomes `WARN`, stale unresolved state remains `FAIL`.

## Deferred

- UI/API wording for `scheduler_running` can be confusing when `SCHEDULER_ENABLED=false` but `NEWS_POLL_ENABLED=true`; this was observed after restart but is not an order-placement integrity issue.
- No autonomous re-enable in this task.

## Risks

- Grace window uses configured confirmation waits plus timeout and a small buffer; if broker callbacks are delayed longer than that, stale mismatches still fail.
- Runtime was restarted to load the code and then kept in safe/read-only mode.
