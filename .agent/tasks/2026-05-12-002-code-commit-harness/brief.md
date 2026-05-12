# Brief

## Metadata

- Task ID: `2026-05-12-002-code-commit-harness`
- Created: `2026-05-12T15:09:10+09:00`
- Repo: `momo-trading`
- Title: Code and commit harness

## Goal

Apply hellforge code-writing and commit guard harness patterns to momo-trading.

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

- /Users/jaewon/my-project/hellforge/docs/workflows/implementation-checklist.md
- /Users/jaewon/my-project/hellforge/docs/workflows/git-workflow.md
- /Users/jaewon/my-project/hellforge/scripts/guard_git_command.py

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
