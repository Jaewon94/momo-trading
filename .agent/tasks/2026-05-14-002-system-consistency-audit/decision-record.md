# Decision Record

## Decision

- Extend `scripts/check_runtime_integrity.py` into a multi-section read-only
  runtime consistency gate: system status, runtime settings, broker/DB pending
  reconciliation, and trade lifecycle integrity.
- Keep lifecycle `WARN/FAIL`, order reconciliation drift, stopped live
  scheduler/agent, and disabled dangerous-action confirmation visible in one
  failing command.
- Make holdings reconciliation default to dry-run and require explicit apply
  flags for backfill, zero-price repair, and missing/quantity close repair.
- Require server-side confirmation tokens for protected admin POST routes that
  can affect broker orders or runtime DB repair/reset.
- Keep scheduled/startup portfolio sync behavior backward compatible by making
  the new `dry_run` parameters optional and defaulting them to apply mode for
  existing internal callers.

## Rationale

- The earlier gap was not just trade lifecycle. Pending order reconciliation,
  runtime safety settings, and protected admin repair routes were separate
  surfaces that could drift without the main gate noticing.
- A POST route should not perform DB repair as a side effect when the operator
  intended a consistency check. Dry-run default makes the contract explicit.
- UI confirmation alone is not a reliable backend safety boundary. The server
  should verify a short-lived action token for protected operations.

## Deferred

- Live DB repair for unpaired SELL rows, broker-missing open BUY lots, and
  quantity mismatches.
- Runtime setting change to enable dangerous action confirmation on the
  currently running process.
- Restarting the running server to activate code changes.

## Risks

- The running server predates these edits, so the live process still reports
  `ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED=false` and still uses old route
  behavior until restart.
- Enforcing tokens for protected admin POSTs is intentionally stricter; clients
  that bypass the existing admin UI must now request confirmation tokens.
- Runtime lifecycle integrity remains FAIL until operational repair is approved.
