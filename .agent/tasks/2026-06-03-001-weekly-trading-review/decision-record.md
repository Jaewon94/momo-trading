# Decision Record

## Decision

Do not change trading behavior or clean runtime DB in this pass. Report findings and recommend targeted fixes.

## Rationale

The user asked for analysis of weekly behavior, not remediation. The repo controls automated trading and cleanup of runtime DB rows or runtime setting changes could affect future trading state. Read-only inspection found enough evidence to prioritize fixes without taking protected actions.

## Deferred

- Cleanup of 2026-06-03 fixture-like decision events in `runtime/data/app.db`.
- Cleanup or benchmark exclusion of 2026-06-04 fixture-like `005930` decision events in `runtime/data/app.db`.
- Changing runtime settings from autonomous/full to safer modes.
- Implementing code fixes for confirmation reconciliation, daily report truth source, and test contamination prevention.
- Harmonizing daily report PnL and performance summary PnL to one canonical trade/account metric.
- Reviewing the `fast_gate_score` inverted-signal warning after a larger forward-return sample.

## Risks

- Active persisted runtime settings are more aggressive than `.env`, so next regular trading session may run autonomous full submission unless intentionally changed.
- `CONFIRM_FAILED`/partial fill paths can leave holdings review without an open BUY row and degrade sell/hold decisions.
- Daily report narrative can be misleading because the LLM prompt did not include enough concrete trade rows despite trade data existing.
- Decision benchmark and recommendation counts can be inflated by fixture-like runtime rows even when no broker order was actually sent.
- Current broker/DB lifecycle is clean, but historical confirmation failures show the same class of issue can recur under partial/stale confirmation paths.
