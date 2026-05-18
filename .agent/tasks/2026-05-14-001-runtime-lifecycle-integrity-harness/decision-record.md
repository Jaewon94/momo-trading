# Decision Record

## Decision

- Add `scripts/check_runtime_integrity.py` as a read-only gate around the
  existing `/api/v1/admin/trades/lifecycle-integrity` API.
- Keep this gate out of the default `task_harness.py verify` command because
  default verify must work without a running live server.
- Add the runtime gate to `change_harness.py` verification hints for
  trading-sensitive paths.
- Change `DecisionMaker.confirm_and_record()` to return a boolean settlement
  result and make scheduler sell paths log completion/rescan/remove thresholds
  only after confirmed or safely inferred fills.

## Rationale

- The current code harness catches code, docs, secrets, and harness artifact
  drift, but it does not inspect live broker/DB lifecycle state.
- Runtime lifecycle integrity is environment-dependent and can legitimately
  fail because of existing operational drift, so it should be explicit and
  recorded rather than silently bundled into every local commit check.
- Change classification is the right place to remind agents that focused unit
  tests are not enough for order lifecycle changes.
- Existing logs showed order receipt could be interpreted as sell completion.
  Returning the confirmation result keeps order submission and fill completion
  as separate states and prevents a failed/zero-fill confirmation from driving
  success-only scheduler follow-up.

## Deferred

- Applying trade close reconciliation.
- Neutral-closing broker-missing open BUY lots.
- Turning off live `AUTONOMOUS`/`FULL` runtime mode.
- Restarting the live process to apply the code change. The running server
  predates these edits and should be restarted only with explicit approval.

## Risks

- The new gate will fail on the current live state until operational repair is
  approved and completed.
- It depends on the local admin server and broker read APIs being available.
- It is a detection gate, not a repair mechanism.
