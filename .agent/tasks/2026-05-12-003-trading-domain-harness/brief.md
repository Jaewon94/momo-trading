# Brief

## Metadata

- Task ID: `2026-05-12-003-trading-domain-harness`
- Created: `2026-05-12T15:25:44+09:00`
- Repo: `momo-trading`
- Title: Trading domain harness expansion

## Goal

Apply remaining useful Hellforge harness patterns: roles, risk classification, domain pack, PR templates, council/handoff/incident templates.

## Scope

In scope:

- Define the intended code, document, or operations change.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- /Users/jaewon/my-project/hellforge/docs/architecture/risk-approval-model.md
- /Users/jaewon/my-project/hellforge/docs/architecture/quality-evaluation-model.md
- /Users/jaewon/my-project/hellforge/docs/architecture/agent-roles.md
- /Users/jaewon/my-project/hellforge/domain-packs/web-development
- /Users/jaewon/my-project/hellforge/templates

Plan implications:

- Adopt:
- Defer:
- Reject:

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- Add task-specific commands here.
