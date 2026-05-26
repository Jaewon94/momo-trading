# Brief

## Metadata

- Task ID: `2026-05-20-003-hold-extension-review`
- Created: `2026-05-20T17:09:38+09:00`
- Repo: `momo-trading`
- Title: Add AI hold extension review

## Goal

Add explicit AI-reviewed horizon extension from MID to LONG and beyond 30 days instead of unconditional max-hold liquidation when trend and risk conditions support continued holding.

## Scope

In scope:

- Add an explicit overnight `EXTEND` decision path for max-hold review.
- Persist extension state in `TradeResult.notes` so later reviews use the extended horizon/limit.
- Keep deterministic hard guards as the fallback when LLM review fails or total hold cap is reached.
- Update focused tests and task verification notes.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Not applicable

Plan implications:

- Adopt: LLM can recommend `EXTEND`, but code enforces review timing and a total hold cap.
- Adopt: MID max-hold extension promotes to LONG; LONG extensions are reviewed in 15-day windows.
- Defer: intraday holdings-review prompt changes unless needed by the overnight liquidation path.
- Reject: unconditional sell solely because MID reached 15 days or LONG reached 30 days when LLM explicitly approves extension.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- Focused unit tests for holding-policy extension metadata.
- Focused scheduler smart-liquidation test for LLM `EXTEND`.
- Prompt test for `EXTEND` schema and extension context.
