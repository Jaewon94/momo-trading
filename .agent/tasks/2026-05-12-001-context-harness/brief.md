# Brief

## Metadata

- Task ID: `2026-05-12-001-context-harness`
- Created: `2026-05-12`
- Requested by: user
- Repo: `momo-trading`
- Source reference: `/Users/jaewon/my-project/hellforge`
- Primary runtime: Codex
- Original request language: Korean
- Final report language: Korean

## Goal

Apply practical context engineering and harness engineering from hellforge to momo-trading so future work has stable project context, task artifacts, and validation checks.

## Scope

In scope:

- Add repo-level agent guidance.
- Add `.agent` project card, security policy, current task pointer, and current task artifacts.
- Add local scripts to create/status/log/verify task artifacts.
- Add tests for the harness validator and task CLI.

Out of scope:

- Running model runtimes automatically.
- Creating branches, worktrees, commits, PRs, or GitHub Actions workflows.
- Changing trading strategy behavior in this task.
- Resetting DB or touching broker state.

## Constraints

- Do not change unrelated trading behavior.
- Do not overwrite existing dirty worktree changes.
- Keep the harness file-based and dependency-free.
- Human-facing docs are Korean where useful; schema and code contracts remain English.

## Context

- hellforge uses `project-card.md`, task briefs, state files, run logs, decision records, test plans, and final reports as durable context.
- momo-trading has frequent operational/debugging work around port `9000`, broker state, LLM providers, trade gates, and admin UI.
- This repo already has many focused tests; the harness should add a small focused test surface instead of broad unrelated test runs.

## Research Gate

Sources checked:

- `/Users/jaewon/my-project/hellforge/docs/foundations/context-engineering.md`
- `/Users/jaewon/my-project/hellforge/docs/foundations/harness-engineering.md`
- `/Users/jaewon/my-project/hellforge/docs/workflows/self-harness.md`
- `/Users/jaewon/my-project/hellforge/scripts/check_task_harness.py`
- `/Users/jaewon/my-project/hellforge/scripts/task_harness.py`

Plan implications:

- Adopt: repo-local project card, task artifact contract, current task pointer, strict-current validation, dependency-free scripts.
- Defer: Agent Council runtime, Discord/OpenACP integration, branch/worktree automation, CI workflow wiring.
- Reject: copying hellforge wholesale; momo-trading needs a smaller self-harness.
- Not applicable: competitor service research, because this task is internal engineering workflow.

## Decision Points

- Use file-based artifacts first; move to SQLite only if task volume or automation requires it.
- Validate the current task strictly while allowing older tasks to be introduced later with warnings.
- Keep broker/runtime safety policy in `.agent/security-policy.md`.

## Completion Criteria

- `.agent/project-card.md` and `.agent/security-policy.md` exist.
- Current task has required artifact files.
- `scripts/check_task_harness.py --strict-current` passes.
- Harness tests pass.
- Remaining limitations are documented.

## Verification Plan

Automated checks:

- `python scripts/check_task_harness.py --strict-current`
- `python -m pytest tests/scripts/test_check_task_harness.py tests/scripts/test_task_harness.py -q`

Manual checks:

- Ensure added files do not modify trading runtime behavior.
- Ensure docs describe protected broker/DB areas.

Security checks:

- No secrets or API keys are added.
- No DB reset or broker action is performed.

## Approval Requirements

Requires approval before:

- git push
- PR creation
- deploy
- migration
- DB reset/delete
- broker-affecting command
